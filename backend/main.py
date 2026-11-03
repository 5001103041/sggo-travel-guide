# -*- coding: utf-8 -*-
"""
main.py - BACKEND REST API CHO DỰ ÁN SGGO! TRAVEL GUIDE
Môn học: Công nghệ Phần mềm (COMP1044)

Kiến trúc rõ ràng, dễ hiểu:
1. Module CSDL: SQLite (qua backend.database)
2. Module AI & GPS: Google Gemini AI + OpenStreetMap Nominatim Geocoding
3. Module Thuật toán: Nearest Neighbor (Haversine Distance)
4. Phân quyền: Khách vãng lai, Thành viên và Quản trị viên (Admin)
"""

import os
import json
import math
import re
import unicodedata
import urllib.request
import urllib.parse
from fastapi import FastAPI, HTTPException, Body, Response, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Tuple

from backend.database import (
    init_db, authenticate_user, register_user,
    get_all_places, get_place_by_id, add_place, update_place, delete_place,
    generate_sample_csv, generate_sample_excel, import_csv_data, import_file_data, import_excel_data,
    get_connection, get_all_users, update_user_role, delete_user,
    toggle_hide_place, save_itinerary, get_import_logs,
    get_all_tags, add_tag, update_tag, delete_tag, toggle_tag_active,
    expand_address_abbreviations
)
import datetime

# 22 ĐƠN VỊ HÀNH CHÍNH CHUẨN CỦA TP. HỒ CHÍ MINH
TPHCM_DISTRICTS = [
    "Quận 1", "Quận 3", "Quận 4", "Quận 5", "Quận 6", "Quận 7", "Quận 8", 
    "Quận 10", "Quận 11", "Quận 12", "Bình Thạnh", "Phú Nhuận", "Gò Vấp", 
    "Tân Bình", "Tân Phú", "Bình Tân", "TP. Thủ Đức", 
    "Hóc Môn", "Củ Chi", "Bình Chánh", "Nhà Bè", "Cần Giờ"
]
VALID_DISTRICTS = set(TPHCM_DISTRICTS) | {
    "Quận Bình Thạnh", "Quận Phú Nhuận", "Quận Gò Vấp", "Quận Tân Bình", "Quận Tân Phú", "Quận Bình Tân",
    "Thành phố Thủ Đức", "Thủ Đức",
    "Huyện Hóc Môn", "Huyện Củ Chi", "Huyện Bình Chánh", "Huyện Nhà Bè", "Huyện Cần Giờ",
    "TP.HCM"
}

def require_admin(x_user_role: Optional[str] = Header(None, alias="X-User-Role")):
    """Bảo mật RBAC: Kiểm tra vai trò của người gọi API, từ chối 403 Forbidden nếu không phải admin"""
    if x_user_role != "admin":
        raise HTTPException(status_code=403, detail="Truy cập bị từ chối: Yêu cầu quyền Quản trị viên (Admin)!")
    return x_user_role

# Tự động đọc file .env
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

# Khởi tạo CSDL SQLite khi server bật
init_db()

app = FastAPI(title="SGGo! Travel Guide API", version="2.0.0")

# Cấu hình CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_for_dev(request, call_next):
    response = await call_next(request)
    path = request.url.path.lower()
    if path.endswith((".js", ".css", ".html")) or path == "/" or path.endswith("/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Khởi tạo Gemini AI Client
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
ai_client = None
if GEMINI_KEY:
    try:
        from google import genai
        ai_client = genai.Client(api_key=GEMINI_KEY)
    except Exception:
        ai_client = None

# ==============================================================================
# PYDANTIC DATA MODELS
# ==============================================================================

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str

class QuickRecommendRequest(BaseModel):
    category: Optional[str] = "all"      # 'an_uong', 'di_choi'
    context: Optional[str] = "all"       # 'di_1_minh', 'nguoi_yeu', 'ban_be', 'gia_dinh'
    price_level: Optional[str] = "all"   # 'under_50k', '50k_100k', '100k_250k', 'above_250k', 'custom', 'all'
    custom_budget: Optional[int] = None
    offset: Optional[int] = 0
    client_time: Optional[str] = None    # Giờ kiểm tra (HH:MM) để lọc quán mở/đóng
    user_lat: Optional[float] = None     # Tọa độ GPS người dùng (Vĩ độ)
    user_lon: Optional[float] = None     # Tọa độ GPS người dùng (Kinh độ)
    prioritize_distance: Optional[bool] = False # Có bật ưu tiên khoảng cách gần tôi không

class UserRoleUpdate(BaseModel):
    role: str

class ExtractGmapsRequest(BaseModel):
    url_or_query: str

class ItineraryRequest(BaseModel):
    user_id: Optional[int] = None
    start_location: str
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    free_time: str                       # Giờ rảnh: '14:00 - 18:30', '19:00 - 22:30', etc.
    companion: Optional[str] = "ban_be"  # 'di_1_minh', 'nguoi_yeu', 'ban_be', 'gia_dinh'
    purpose: Optional[str] = "ca_hai"    # 'an_uong', 'di_choi', 'ca_hai'
    takenote: Optional[str] = ""         # Ghi chú / Loại trừ địa điểm
    context: Optional[str] = ""          # Giữ tương thích ngược
    budget: Optional[str] = None
    budget_level: Optional[str] = None
    target_budget: Optional[int] = None
    num_stops: Optional[int] = 3         # Số trạm dừng mong muốn (2, 3, 4 - mặc định 3)
    radius_km: Optional[float] = None    # Giới hạn bán kính quanh điểm xuất phát (km)
    shuffle_seed: Optional[int] = 0      # Dùng cho G6-FR06: Xáo trộn / Đổi phương án khác
    ai_model: Optional[str] = "gemini-3.5-flash-lite"

class PlaceModel(BaseModel):
    name: str
    category: str
    address: str
    district: Optional[str] = "TP.HCM"
    lat: Optional[float] = None
    lon: Optional[float] = None
    open_time: Optional[str] = ""
    close_time: Optional[str] = ""
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    peak_hours: Optional[str] = ""
    best_review: Optional[str] = ""
    worst_review: Optional[str] = ""
    image_url: Optional[str] = None
    tags: Optional[str] = "nhom_ban"
    is_verified: Optional[int] = 1
    is_verified_review: Optional[int] = 1
    is_admin_choice: Optional[int] = 0
    is_hidden: Optional[int] = 0
    price_display: Optional[str] = None
    hours_display: Optional[str] = None
    google_maps_url: Optional[str] = None

# ==============================================================================
# THUẬT TOÁN ĐỊNH TUYẾN & GPS (HAVERSINE NEAREST NEIGHBOR)
# ==============================================================================

def remove_accent(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để tìm kiếm không phân biệt dấu"""
    text = unicodedata.normalize('NFD', text)
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn').lower()

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Tính khoảng cách đường tròn lớn giữa 2 tọa độ GPS (km)"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

haversine_distance = calculate_haversine_distance

def resolve_start_coords(location_str: str):
    """
    Geocoding điểm xuất phát:
    1. Ưu tiên tra cứu nhanh các địa danh/trường học/chợ nổi tiếng tại Quận 5 (0ms).
    2. Nếu không có trong danh mục nhanh -> Gọi OpenStreetMap Nominatim.
    3. Nếu không tìm thấy hoặc mất mạng -> Fallback về tọa độ trung tâm Quận 5.
    """
    loc_clean = location_str.strip()
    loc_norm = remove_accent(loc_clean)

    # 1. Bảng toạ độ tức thì cho các địa danh tiêu biểu tại Quận 5
    landmarks = {
        "su pham": (10.7601, 106.6823),
        "280 an duong vuong": (10.7601, 106.6823),
        "an duong vuong": (10.7601, 106.6823),
        "an dong": (10.7573, 106.6713),
        "cho an dong": (10.7573, 106.6713),
        "binh tay": (10.7497, 106.6515),
        "cho binh tay": (10.7497, 106.6515),
        "cho lon": (10.7535, 106.6580),
        "thuan kieu": (10.7554, 106.6577),
        "cho ray": (10.7577, 106.6596),
        "benh vien cho ray": (10.7577, 106.6596),
        "y duoc": (10.7562, 106.6589),
        "dai hoc y duoc": (10.7562, 106.6589),
        "van lang": (10.7585, 106.6705),
        "cong vien van lang": (10.7585, 106.6705),
        "hung vuong": (10.7570, 106.6625),
        "dai the gioi": (10.7530, 106.6690),
        "ben thanh": (10.7725, 106.6980),
        "cho ben thanh": (10.7725, 106.6980),
        "nha tho duc ba": (10.7798, 106.6990),
        "sai gon": (10.7554, 106.6577)
    }
    for k, coords in landmarks.items():
        if k in loc_norm:
            return coords

    # 2. Gọi Nominatim nếu là địa chỉ lạ
    try:
        query = f"{loc_clean}, Ho Chi Minh City, Vietnam"
        url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
            "q": query, "format": "json", "limit": 1
        })
        req = urllib.request.Request(url, headers={"User-Agent": "SGGo-Travel-Guide-D5/2.0"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            data = json.loads(resp.read().decode())
            if data and len(data) > 0:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass

    # 3. Mặc định: Tâm Quận 5 (Khu vực Thuận Kiều Plaza / Hồng Bàng)
    return 10.7554, 106.6577

def optimize_route_nearest_neighbor(start_coords, candidates, max_stops=3):
    """Thuật toán láng giềng gần nhất (Nearest Neighbor) chọn 3 trạm liên hoàn thuận đường"""
    current_lat, current_lon = start_coords
    unvisited = list(candidates)
    route = []

    for _ in range(min(max_stops, len(candidates))):
        nearest_node = None
        min_dist = float('inf')

        for place in unvisited:
            p_lat = place.get("lat")
            p_lon = place.get("lon")
            if not p_lat or not p_lon:
                continue
            dist = calculate_haversine_distance(current_lat, current_lon, float(p_lat), float(p_lon))
            if dist < min_dist:
                min_dist = dist
                nearest_node = place

        if nearest_node:
            dist_km = round(min_dist, 2)
            travel_min = max(3, int(round(dist_km * 3.5))) # Ước tính 3.5 phút/km xe máy Sài Gòn
            node_copy = dict(nearest_node)
            node_copy["dist_km"] = dist_km
            node_copy["travel_minutes"] = travel_min
            route.append(node_copy)
            current_lat, current_lon = nearest_node["lat"], nearest_node["lon"]
            unvisited.remove(nearest_node)

    return route

def calculate_traffic_speed_model(dist_km: float, clock_min: int):
    """
    Mô hình vận tốc xe máy biến thiên theo khung giờ thực tế tại TP.HCM (Time-Varying Traffic Speed Model):
    - Giờ cao điểm sáng (07:00 - 09:00) & chiều tan tầm (16:30 - 19:00): 4.8 phút/km (~12.5 km/h)
    - Giờ bình thường (09:00 - 16:30 & 19:00 - 21:00): 3.0 phút/km (~20 km/h)
    - Đêm khuya / Sáng sớm (21:00 - 07:00): 2.2 phút/km (~27 km/h)
    """
    h = (clock_min // 60) % 24
    m = clock_min % 60
    t_val = h + m / 60.0

    if (7.0 <= t_val <= 9.0) or (16.5 <= t_val <= 19.0):
        factor = 4.8
        status = f"Giờ cao điểm ({h:02d}:{m:02d}), mật độ xe cộ đông, chú ý kẹt xe."
        badge = "Cao điểm"
    elif t_val >= 21.0 or t_val < 7.0:
        factor = 2.2
        status = f"Khung giờ đêm khuya ({h:02d}:{m:02d}), đường phố thông thoáng, chạy xe êm."
        badge = "Đường vắng"
    else:
        factor = 3.0
        status = f"Khung giờ bình thường ({h:02d}:{m:02d}), giao thông ổn định, lưu thông vừa phải."
        badge = "Bình thường"

    t_min = max(3, int(round(dist_km * factor)))
    return t_min, status, badge

def get_osrm_route_legs(coords: List[Tuple[float, float]], timeout: float = 5.0) -> Optional[List[float]]:
    """
    Gọi OSRM API mã nguồn mở (OpenStreetMap) để lấy cự ly đường phố thực tế chính xác từng mét.
    Nếu timeout hoặc lỗi mạng -> trả về None để tự động fallback sang Haversine * 1.25.
    """
    try:
        coord_str = ';'.join(f'{lon},{lat}' for lat, lon in coords)
        url = f'http://router.project-osrm.org/route/v1/driving/{coord_str}?overview=false'
        req = urllib.request.Request(url, headers={'User-Agent': 'SGGoTravelGuide/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            data = json.loads(res.read().decode())
        if data.get('code') == 'Ok':
            routes = data.get('routes', [])
            if routes and 'legs' in routes[0]:
                return [round(leg['distance'] / 1000.0, 2) for leg in routes[0]['legs']]
    except Exception:
        pass
    return None

def get_natural_dwell_bounds(spot: dict) -> Tuple[int, int, int, str]:
    """
    Trả về (min_dwell, default_dwell, max_dwell, group_name) chuẩn tự nhiên theo đúng 7 NHÓM ĐỊA ĐIỂM HỌC THUẬT:
    - Nhóm 1 (ID 1 - 49): Cà phê, Trà sữa, Tiệm bánh & Kem, Chè (45 - 90 phút, chuẩn 60p)
    - Nhóm 2 (ID 50 - 63): Workshop Thủ công & Trải nghiệm Nghệ thuật (75 - 150 phút, chuẩn 105p)
    - Nhóm 3 (ID 64 - 100): Quán Lẩu, Nướng BBQ, Quán Ốc & Quán Nhậu (70 - 120 phút, chuẩn 90p)
    - Nhóm 4 (ID 101 - 140): Gà rán, Mì cay, Pizza, Fastfood & Đồ Hàn/Nhật (45 - 90 phút, chuẩn 60p)
    - Nhóm 5 (ID 141 - 160): Quán Ăn truyền thống Sài Gòn (Phở, Cơm tấm, Hủ tiếu) (30 - 50 phút, chuẩn 40p)
    - Nhóm 6 (ID 161 - 180): Trung tâm Thương mại & Khu mua sắm Phức hợp (60 - 100 phút, chuẩn 75p)
    - Nhóm 7 (ID 181 - 201): Di tích lịch sử, Bảo tàng, Công viên & Tâm linh (45 - 90 phút, chuẩn 60p)
    """
    pid = spot.get("id")
    if isinstance(pid, int):
        if 1 <= pid <= 49:
            return 45, 60, 90, "Nhóm 1: Cà phê, Trà sữa, Bánh & Kem"
        elif 50 <= pid <= 63:
            return 75, 105, 150, "Nhóm 2: Workshop Thủ công & Nghệ thuật"
        elif 64 <= pid <= 100:
            return 70, 90, 120, "Nhóm 3: Quán Lẩu, Nướng BBQ, Ốc & Nhậu"
        elif 101 <= pid <= 140:
            return 45, 60, 90, "Nhóm 4: Gà rán, Mì cay, Pizza, Fastfood"
        elif 141 <= pid <= 160:
            return 30, 40, 50, "Nhóm 5: Quán Ăn truyền thống (Phở, Cơm tấm, Hủ tiếu)"
        elif 161 <= pid <= 180:
            return 60, 75, 100, "Nhóm 6: Trung tâm Thương mại & Chợ đầu mối"
        elif 181 <= pid <= 201:
            return 45, 60, 90, "Nhóm 7: Di tích lịch sử, Bảo tàng & Tâm linh"

    # Fallback dự phòng theo từ khóa nếu địa điểm do Admin thêm mới ngoài ID 1-201
    cat = spot.get("category", "")
    name_norm = remove_accent(spot.get("name", "")).lower()
    review_norm = remove_accent(spot.get("best_review", "") or "").lower()
    text = name_norm + " " + review_norm

    if any(k in text for k in ["workshop", "nen", "candle", "gom", "ve tranh", "ban cung"]):
        return 75, 105, 150, "Nhóm 2: Workshop Thủ công & Nghệ thuật"
    if any(k in text for k in ["lau", "nuong", "bbq", "buffet", "hai san", "oc", "quan nhau"]):
        return 70, 90, 120, "Nhóm 3: Quán Lẩu, Nướng BBQ, Ốc & Nhậu"
    if any(k in text for k in ["ga ran", "kfc", "lotteria", "bonchon", "jollibee", "pizza", "mi cay", "dookki"]):
        return 45, 60, 90, "Nhóm 4: Gà rán, Mì cay, Pizza, Fastfood"
    if any(k in text for k in ["che", "kem", "gelato", "trang mieng", "banh trang", "cafe", "coffee", "kafe", "tra sua"]):
        return 45, 60, 90, "Nhóm 1: Cà phê, Trà sữa, Bánh & Kem"
    if any(k in text for k in ["mall", "centre", "plaza", "cho ben thanh", "cho binh tay"]):
        return 60, 75, 100, "Nhóm 6: Trung tâm Thương mại & Chợ đầu mối"
    if cat == "di_choi":
        return 45, 60, 90, "Nhóm 7: Di tích lịch sử, Bảo tàng & Tâm linh"
    return 30, 40, 50, "Nhóm 5: Quán Ăn truyền thống (Phở, Cơm tấm, Hủ tiếu)"

def calculate_proportional_dwell_times(places: list, free_duration: int, total_travel_minutes: int) -> list:
    """
    Mô hình Phân bổ Quỹ thời gian Động theo Trọng số Danh mục (Dynamic Proportional Time-Budget Allocation Model):
    Tự động cân đối thời gian dừng chân tại từng quán dựa trên tổng quỹ thời gian rảnh trừ đi thời gian di chuyển,
    nhân với trọng số của từng loại hình quán.
    """
    def get_weight(spot):
        cat = spot.get("category", "")
        name_norm = remove_accent(spot.get("name", "")).lower()
        if cat == "di_choi":
            return 1.0
        if any(w in name_norm for w in ["cafe", "kafe", "coffee", "tra", "che", "kem", "sinh to", "an vat", "banh mi"]):
            return 0.8
        if any(w in name_norm for w in ["lau", "nuong", "bbq", "hai san", "nha hang", "oc"]):
            return 1.4
        return 1.2

    weights = [get_weight(p) for p in places]
    total_w = sum(weights) or 1.0
    stay_budget = max(len(places) * 20, free_duration - total_travel_minutes)
    
    raw_dwells = [int(round((stay_budget * w) / total_w)) for w in weights]
    clamped = [max(20, min(120, d)) for d in raw_dwells]
    return clamped

def estimate_dwell_time(spot: dict) -> int:
    """Ước tính thời gian lưu lại phù hợp với đặc thù từng quán/địa điểm (phút)"""
    cat = spot.get("category", "")
    name_norm = remove_accent(spot.get("name", "")).lower()

    if cat == "di_choi":
        return 40  # Điểm di tích, bảo tàng, check-in công viên

    if any(w in name_norm for w in ["cafe", "kafe", "coffee", "tra sua", "che", "kem", "sinh to", "banh mi", "an vat", "nuoc ep"]):
        return 30
    if any(w in name_norm for w in ["lau", "nuong", "bbq", "hai san", "nha hang", "oc", "quan nhau"]):
        return 60
    return 45

def find_budget_optimal_route(start_coords, candidates_pool, target_budget: int = 0, max_stops: int = 3):
    """
    Tối ưu hóa đa mục tiêu: Chọn max_stops trạm vừa gần nhất (TSP Nearest Neighbor)
    vừa đảm bảo tổng chi phí tối thiểu <= target_budget (G6-FR05 MUST).
    """
    if len(candidates_pool) <= max_stops:
        return optimize_route_nearest_neighbor(start_coords, candidates_pool, max_stops=max_stops)

    import itertools
    pool = candidates_pool[:12]

    if target_budget > 0:
        valid_routes = []
        for combo in itertools.combinations(pool, max_stops):
            cost = sum(p.get("min_price", 0) for p in combo)
            if cost <= target_budget:
                ordered = optimize_route_nearest_neighbor(start_coords, list(combo), max_stops=max_stops)
                if ordered:
                    total_d = calculate_haversine_distance(start_coords[0], start_coords[1], ordered[0].get("lat") or 10.75, ordered[0].get("lon") or 106.66)
                    for i in range(len(ordered) - 1):
                        total_d += calculate_haversine_distance(
                            ordered[i].get("lat") or 10.75, ordered[i].get("lon") or 106.66,
                            ordered[i+1].get("lat") or 10.75, ordered[i+1].get("lon") or 106.66
                        )
                    valid_routes.append((total_d, cost, ordered))

        if valid_routes:
            valid_routes.sort(key=lambda x: x[0])
            return valid_routes[0][2]

    return optimize_route_nearest_neighbor(start_coords, pool, max_stops=max_stops)

# ==============================================================================
# CÁC API XÁC THỰC TÀI KHOẢN (AUTH)
# ==============================================================================

@app.post("/api/auth/login")
def login(req: LoginRequest):
    user = authenticate_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu!")
    return {"status": "ok", "user": user}

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    u = (req.username or "").strip()
    if not re.match(r'^[a-zA-Z0-9_]{3,30}$', u):
        raise HTTPException(status_code=400, detail="Tên tài khoản phải từ 3 đến 30 ký tự, chỉ gồm chữ cái, số và dấu gạch dưới (_), không chứa khoảng trắng!")
        
    p = req.password or ""
    if len(p) < 6:
        raise HTTPException(status_code=400, detail="Mật khẩu phải có tối thiểu 6 ký tự để đảm bảo an toàn!")
        
    fn = (req.full_name or "").strip()
    if len(fn) < 2:
        raise HTTPException(status_code=400, detail="Họ và tên phải có tối thiểu 2 ký tự!")

    user = register_user(u, p, fn)
    if not user:
        raise HTTPException(status_code=400, detail="Tên tài khoản này đã có người sử dụng!")
    return {"status": "ok", "user": user}

# ==============================================================================
# CÁC API ĐỊA ĐIỂM (PLACES & SEARCH TỪ A ĐẾN Z)
# ==============================================================================

@app.get("/health")
@app.get("/api/health")
def health_check():
    """Kiểm tra tình trạng hoạt động của máy chủ backend (Health check)"""
    return {"status": "healthy", "service": "sggo-travel-guide"}

@app.get("/api/places")
def get_places(category: Optional[str] = None, tag: Optional[str] = None, 
               min_price: Optional[int] = None, max_price: Optional[int] = None,
               min_rating: Optional[float] = None, search: Optional[str] = None,
               only_verified: Optional[bool] = True, include_hidden: Optional[bool] = False):
    return get_all_places(category=category, context_tag=tag, min_budget=min_price, 
                          max_budget=max_price, min_rating=min_rating, search=search, 
                          only_verified=only_verified, include_hidden=include_hidden)

@app.get("/api/places/{place_id}")
def get_place(place_id: int):
    place = get_place_by_id(place_id)
