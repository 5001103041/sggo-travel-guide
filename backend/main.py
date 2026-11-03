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
    if not place:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa điểm này.")
    return place

# ==============================================================================
# API GỢI Ý NHANH (QUICK RECOMMENDATION - 5 MỨC NGÂN SÁCH & TỰ NHẬP)
# ==============================================================================

def parse_place_tiers(place):
    """
    Bóc tách cấu trúc 2-Tier:
    - Nếu chuỗi có định dạng tier1:...|tier2:...: bóc tách chính xác từng Tier.
    - Nếu chuỗi dạng cũ phân tách dấu phẩy (tag1,tag2,tag3,tag4): 2 tag đầu là Tier 1, còn lại là Tier 2.
    """
    tags_str = (place.get("tags") or "").strip()
    if not tags_str:
        return [], []
    if "tier1:" in tags_str or "tier2:" in tags_str:
        parts = tags_str.split("|")
        t1, t2 = [], []
        for p in parts:
            p = p.strip()
            if p.startswith("tier1:"):
                t1 = [x.strip() for x in p.replace("tier1:", "").split(",") if x.strip()]
            elif p.startswith("tier2:"):
                t2 = [x.strip() for x in p.replace("tier2:", "").split(",") if x.strip()]
        return t1, t2
    else:
        all_tags = [x.strip() for x in tags_str.split(",") if x.strip()]
        return all_tags[:2], all_tags[2:]


def get_companion_tier_score(place, mapped_tag):
    """
    Mô hình Phân Tầng 2 Bậc (2-Tier Fit Model):
    - Tier 1 (Cốt lõi - Phù hợp xuất sắc): +20.0 điểm cho MỌI tag thuộc Tier 1 (CÙNG TIER THÌ CÙNG ĐIỂM)
    - Tier 2 (Khả dụng / Thứ cấp): +12.0 điểm cho MỌI tag thuộc Tier 2 (CÙNG TIER THÌ CÙNG ĐIỂM)
    - Không có tag: -10.0 điểm
    """
    if not mapped_tag:
        return 0.0, None
    t1, t2 = parse_place_tiers(place)
    if mapped_tag in t1:
        return 20.0, 1
    elif mapped_tag in t2:
        return 12.0, 2
    else:
        return -10.0, None


@app.post("/api/quick-recommend")
def quick_recommend(req: QuickRecommendRequest):
    """
    Thuật toán phân tích ma trận đa chiều & Chấm điểm độ phù hợp (Smart Scoring):
    1. Lọc thể loại (category): Ẩm thực hoặc Vui chơi
    2. Điểm tương thích đồng hành (context): đi 1 mình, cặp đôi, nhóm bạn, gia đình (chuẩn hóa 2-Tier)
    3. Điểm khớp ngân sách (budget): <50k, 50k-100k, 100k-250k, >250k hoặc số tiền tự nhập
    4. Trọng số uy tín (rating, reviews)
    5. Hỗ trợ offset xoay vòng (Đổi gợi ý khác) không bao giờ bị trùng lặp cứng nhắc
    """
    all_places = get_all_places(category=req.category, include_hidden=False)
    if not all_places:
        all_places = get_all_places(include_hidden=False)

    tag_mapping = {
        "di_1_minh": "di_1_minh",
        "nguoi_yeu": "hen_ho",
        "ban_be": "nhom_ban",
        "gia_dinh": "gia_dinh"
    }
    mapped_tag = tag_mapping.get(req.context, None)

    scored_places = []
    for p in all_places:
        score = 0.0
        p_dict = dict(p)

        # 1. Khớp Category
        if req.category and req.category != "all" and p.get("category") != req.category:
            continue

        # 2. Khớp Context (Đồng hành) - Mô hình 2-Tier Chuẩn Xác (Cùng Tier thì Cùng Điểm)
        tier_pts, fit_tier = get_companion_tier_score(p, mapped_tag)
        score += tier_pts
        p_dict["fit_tier"] = fit_tier

        # 2.5 Kiểm tra trạng thái mở cửa (Business Rule 2: Loại trừ 100% quán đang đóng cửa)
        check_t = req.client_time
        if not check_t:
            now_vn = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
            check_t = now_vn.strftime("%H:%M")
        is_open_now = is_place_open_at_time(p, check_t)
        p_dict["is_currently_open"] = is_open_now
        if not is_open_now:
            # Loại bỏ hoàn toàn quán đóng cửa khỏi gợi ý khám phá
            continue
        score += 15.0

        # 3. Khớp Ngân sách (Loại trừ tuyệt đối các quán vi phạm giới hạn ngân sách)
        min_p = p.get("min_price", 0)
        max_p = p.get("max_price", 0)
        avg_p = (min_p + max_p) / 2.0

        if req.price_level == "free":
            # Khi chọn Miễn phí (0đ): BẮT BUỘC giá phải là 0đ (loại bỏ tuyệt đối quán có thu phí)
            if not (min_p == 0 and max_p == 0):
                continue
            score += 35.0
        elif p.get("category") == "di_choi" and min_p == 0 and max_p == 0:
            if req.price_level == "under_50k":
                score += 20.0
            elif req.price_level == "50k_100k":
                score += 10.0
            else:
                score += 5.0
        else:
            if req.price_level == "under_50k":
                # Dưới 50k: Quán phải có giá tối thiểu <= 65k (loại bỏ dứt điểm các quán đắt tiền 100k, 200k)
                if min_p > 65000:
                    continue
                if max_p <= 55000:
                    score += 25.0
                else:
                    score += 15.0
            elif req.price_level == "50k_100k":
                # 50k - 100k: Quán trong khoảng hợp lý [40k, 125k]
                if min_p > 125000 or (max_p > 0 and max_p < 40000):
                    continue
                if 45000 <= avg_p <= 110000:
                    score += 25.0
                else:
                    score += 15.0
            elif req.price_level == "100k_250k":
                # 100k - 250k: Quán trong khoảng [90k, 280k]
                if min_p > 280000 or (max_p > 0 and max_p < 85000):
                    continue
                if 95000 <= avg_p <= 260000:
                    score += 25.0
                else:
                    score += 15.0
            elif req.price_level == "above_250k":
                # Trên 250k: Trải nghiệm cao cấp
                if max_p > 0 and max_p < 150000:
                    continue
                if max_p >= 250000:
                    score += 25.0
                else:
                    score += 15.0
            elif req.price_level == "custom" and req.custom_budget and req.custom_budget > 0:
                cb = req.custom_budget
                if min_p > cb * 1.3:
                    continue
                ratio = min(avg_p, cb) / max(avg_p, cb, 1)
                score += 25.0 * ratio

        # 4. Trọng số Đánh giá (Rating & Reviews)
        rating = float(p.get("rating", 4.0))
        reviews_count = int(p.get("reviews_count", 0))

        # Điểm số sao: Chuẩn hóa tách mốc trung bình 4.0 (Mean-Centering)
        rating_score = (rating - 4.0) * 4.0

        # Điểm độ uy tín cộng đồng: Biến đổi Logarithmic Scaling log10(reviews + 1) * 2.0
        if rating >= 4.0:
            review_score = math.log10(reviews_count + 1) * 2.0
        else:
            review_score = -math.log10(reviews_count + 1) * 1.0

        score += (rating_score + review_score)

        # 5. Điểm Khoảng cách Không gian (Spatial Proximity Scoring) nếu người dùng có vị trí GPS
        if req.user_lat and req.user_lon and p.get("lat") and p.get("lon"):
            try:
                dist_km = calculate_haversine_distance(
                    float(req.user_lat), float(req.user_lon),
                    float(p.get("lat")), float(p.get("lon"))
                )
                p_dict["distance_km"] = round(dist_km, 2)
                
                # Nếu người dùng bật tùy chọn 'Ưu tiên gần tôi':
                if req.prioritize_distance:
                    if dist_km <= 3.0:
                        dist_score = 25.0 - (dist_km / 3.0) * 5.0           # Cực gần <= 3km: +20 đến +25 điểm
                    elif dist_km <= 7.0:
                        dist_score = 20.0 - ((dist_km - 3.0) / 4.0) * 8.0    # Gần 3 - 7km: +12 đến +20 điểm
                    elif dist_km <= 15.0:
                        dist_score = 12.0 - ((dist_km - 7.0) / 8.0) * 10.0   # Vừa phải 7 - 15km: +2 đến +12 điểm
                    else:
                        dist_score = max(-10.0, -((dist_km - 15.0) * 1.5))   # Quá xa > 15km: trừ nhẹ điểm
                    score += dist_score
                    p_dict["distance_score"] = round(dist_score, 1)
            except Exception:
                pass

        scored_places.append((score, p_dict))

    # 1. Xử lý ngân sách tự nhập quá thấp cho ẩm thực (< 20.000đ)
    # Tại TP.HCM không có quán ăn nào dưới 20.000đ. Tự động chuyển hướng gợi ý điểm tham quan/check-in 0đ miễn phí!
    if not scored_places and req.category == "an_uong" and req.price_level == "custom" and req.custom_budget and req.custom_budget < 20000:
        free_places = [p for p in get_all_places(category="di_choi", include_hidden=False) if p.get("min_price", 0) == 0 and p.get("max_price", 0) == 0]
        for p in free_places:
            p_dict = dict(p)
            tier_pts, fit_tier = get_companion_tier_score(p, mapped_tag)
            p_dict["fit_tier"] = fit_tier
            p_dict["free_fallback_notice"] = f"Ngân sách bạn nhập ({req.custom_budget:,}đ) không đủ cho các quán ẩm thực tại TP.HCM (tối thiểu ~20.000đ). SGGo gợi ý các điểm đến tham quan & check-in 0đ phù hợp nhất cho bạn!"
            p_dict["is_currently_open"] = is_place_open_at_time(p, check_t)
            rating = float(p.get("rating", 4.0))
            reviews_count = int(p.get("reviews_count", 0))
            r_score = (rating - 4.0) * 4.0 + (math.log10(reviews_count + 1) * 2.0 if rating >= 4.0 else -math.log10(reviews_count + 1))
            scored_places.append((tier_pts + 35.0 + r_score, p_dict))

    # 2. Xử lý trường hợp: Người dùng chọn Ẩm thực nhưng lại chọn Miễn phí (0đ).
    # Thực tế Sài Gòn không có quán ăn miễn phí 0đ, tự động chuyển hướng tìm các điểm tham quan/check-in 0đ!
    if not scored_places and req.price_level == "free":
        free_places = [p for p in get_all_places(category="di_choi", include_hidden=False) if p.get("min_price", 0) == 0 and p.get("max_price", 0) == 0]
        for p in free_places:
            p_dict = dict(p)
            tier_pts, fit_tier = get_companion_tier_score(p, mapped_tag)
            p_dict["fit_tier"] = fit_tier
            p_dict["free_fallback_notice"] = "Sài Gòn không có quán ăn miễn phí (0đ). SGGo đã gợi ý các điểm đến tham quan & check-in 0đ phù hợp nhất cho bạn!"
            p_dict["is_currently_open"] = is_place_open_at_time(p, check_t)
            rating = float(p.get("rating", 4.0))
            reviews_count = int(p.get("reviews_count", 0))
            r_score = (rating - 4.0) * 4.0 + (math.log10(reviews_count + 1) * 2.0 if rating >= 4.0 else -math.log10(reviews_count + 1))
            scored_places.append((tier_pts + 35.0 + r_score, p_dict))

    # 3. Nếu vào giờ quá khuya không còn quán nào mở cửa trong danh mục
    # CHỈ kích hoạt fallback này nếu thực sự có quán phù hợp danh mục/ngân sách nhưng tất cả đều đang đóng cửa!
    if not scored_places:
        matching_places = [p for p in all_places if (not req.category or req.category == "all" or p.get("category") == req.category)]
        if req.price_level == "custom" and req.custom_budget and req.custom_budget > 0:
            matching_places = [p for p in matching_places if (p.get("min_price", 0) or 0) <= req.custom_budget * 1.3]
        
        if matching_places:
            for p in matching_places:
                p_dict = dict(p)
                p_dict["is_currently_open"] = False
                p_dict["closed_warning"] = "Hiện tại là đêm khuya, các địa điểm phù hợp đã đóng cửa. SGGo gợi ý các điểm sẽ mở cửa sớm nhất vào sáng mai cho bạn!"
                tier_pts, fit_tier = get_companion_tier_score(p, mapped_tag)
                p_dict["fit_tier"] = fit_tier
                scored_places.append((tier_pts + float(p.get("rating", 4.0)), p_dict))

    # Bổ sung khoảng cách cho các địa điểm fallback nếu có GPS
    if req.user_lat and req.user_lon:
        for _, p_dict in scored_places:
            if "distance_km" not in p_dict and p_dict.get("lat") and p_dict.get("lon"):
                try:
                    p_dict["distance_km"] = round(calculate_haversine_distance(
                        float(req.user_lat), float(req.user_lon),
                        float(p_dict.get("lat")), float(p_dict.get("lon"))
                    ), 2)
                except Exception:
                    pass

    # Sắp xếp theo điểm phù hợp giảm dần
    scored_places.sort(key=lambda x: x[0], reverse=True)
    sorted_places = [item[1] for item in scored_places]

    if not sorted_places:
        return []

    # Xử lý xoay vòng gợi ý (offset) để người dùng bấm "Đổi 3 quán khác"
    offset = req.offset or 0
    if offset >= len(sorted_places):
        offset = 0

    results = sorted_places[offset : offset + 3]
    if len(results) < 3 and len(sorted_places) >= 3:
        results.extend(sorted_places[: 3 - len(results)])

    return results

# ==============================================================================
# API LẬP LỘ TRÌNH THÔNG MINH (RULE-BASED + HEURISTIC TSP + GEMINI AI EXPLANATION)
# ==============================================================================

def parse_free_time_minutes(free_time_str: str) -> int:
    """Tính tổng số phút rảnh từ chuỗi thời gian (VD: '14:00 - 18:30' -> 270 phút, '1h6p' -> 66 phút)"""
    if not free_time_str:
        return 240
    # 1. Định dạng khoảng thời gian: "14:00 - 18:30" hoặc "18:00 - 19:06"
    parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', free_time_str)
    if len(parts) >= 2:
        h1, m1 = int(parts[0][0]), int(parts[0][1] or 0)
        h2, m2 = int(parts[1][0]), int(parts[1][1] or 0)
        start_m = h1 * 60 + m1
        end_m = h2 * 60 + m2
        if end_m < start_m:
            end_m += 24 * 60
        return max(15, end_m - start_m)

    # 2. Định dạng thời lượng có cả giờ và phút: "1h6p", "1h 30p", "1 tiếng 6 phút", "1 giờ 30 phút"
    hm_match = re.search(r'(\d+)\s*(?:tiếng|giờ|h)\s*(\d+)\s*(?:phút|p)?', free_time_str, re.IGNORECASE)
    if hm_match:
        h = int(hm_match.group(1))
        m = int(hm_match.group(2))
        return h * 60 + m

    # 3. Định dạng chỉ có giờ: "2h", "3 tiếng", "1.5h"
    h_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:tiếng|giờ|h)', free_time_str, re.IGNORECASE)
    if h_match:
        return int(float(h_match.group(1)) * 60)

    # 4. Định dạng chỉ có phút: "90 phút", "66p"
    m_match = re.search(r'(\d+)\s*(?:phút|p)', free_time_str, re.IGNORECASE)
    if m_match:
        return int(m_match.group(1))

    return 240

def parse_target_budget_amount(req: ItineraryRequest) -> int:
    """Xác định ngân sách mục tiêu dạng số nguyên (VNĐ)"""
    if req.budget_level == "free" or req.budget == "free" or req.target_budget == 0:
        return 0
    if req.target_budget is not None and req.target_budget > 0:
        return req.target_budget
    lvl = req.budget_level or req.budget or "100k_250k"
    if lvl == "free":
        return 0
    elif lvl == "under_100k":
        return 100000
    elif lvl == "100k_250k":
        return 250000
    elif lvl == "above_250k":
        return 500000
    return 250000

def is_place_open_at_time(p: dict, check_time_str: str) -> bool:
    """Kiểm tra quán có đang mở cửa tại thời điểm check_time_str (HH:MM) không (Business Rule 2)"""
    ot = p.get("open_time")
    ct = p.get("close_time")
    if not ot or not ct or ot == "Chưa rõ" or ct == "Chưa rõ":
        return True
    try:
        parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', check_time_str)
        if not parts:
            return True
        check_mins = int(parts[0][0]) * 60 + int(parts[0][1] or 0)

        ot_parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', ot)
        ct_parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', ct)
        if not ot_parts or not ct_parts:
            return True
        p_start = int(ot_parts[0][0]) * 60 + int(ot_parts[0][1] or 0)
        p_end = int(ct_parts[0][0]) * 60 + int(ct_parts[0][1] or 0)

        if p_start == p_end:
            return True

        if p_end < p_start:
            return check_mins >= p_start or check_mins <= p_end
        else:
            return p_start <= check_mins <= p_end
    except Exception:
        return True

def is_place_open_during_window(p: dict, free_time_str: str) -> bool:
    """Kiểm tra quán có mở cửa trong khung giờ rảnh không (Business Rule 2)"""
    ot = p.get("open_time")
    ct = p.get("close_time")
    if not ot or not ct or ot == "Chưa rõ" or ct == "Chưa rõ":
        return True
    try:
        parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', free_time_str)
        if len(parts) >= 2:
            req_start = int(parts[0][0]) * 60 + int(parts[0][1] or 0)
            req_end = int(parts[1][0]) * 60 + int(parts[1][1] or 0)
        elif len(parts) == 1:
            req_start = int(parts[0][0]) * 60 + int(parts[0][1] or 0)
            req_end = req_start + 120
        else:
            return True

        ot_parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', ot)
        ct_parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', ct)
        if not ot_parts or not ct_parts:
            return True
        p_start = int(ot_parts[0][0]) * 60 + int(ot_parts[0][1] or 0)
        p_end = int(ct_parts[0][0]) * 60 + int(ct_parts[0][1] or 0)

        if p_start == p_end:
            return True

        req_windows = []
        if req_end < req_start:
            req_windows.append((req_start, 1440))
            req_windows.append((0, req_end))
        else:
            req_windows.append((req_start, req_end))

        place_windows = []
        if p_end < p_start:
            place_windows.append((p_start, 1440))
            place_windows.append((0, p_end))
        else:
            place_windows.append((p_start, p_end))

        for rw_start, rw_end in req_windows:
            for pw_start, pw_end in place_windows:
                overlap_start = max(rw_start, pw_start)
                overlap_end = min(rw_end, pw_end)
                if overlap_end - overlap_start >= 15:
                    return True
        return False
    except Exception:
        return True

def check_peak_hours_overlap(arr_min: int, dep_min: int, peak_str: Optional[str]) -> Tuple[bool, str]:
    """Kiểm tra thời gian dừng chân của khách có trùng giờ cao điểm quán không"""
    if not peak_str:
        return False, ""
    try:
        windows = peak_str.split("&")
        for w in windows:
            parts = w.strip().split("-")
            if len(parts) == 2:
                ot_parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', parts[0].strip())
                ct_parts = re.findall(r'(\d{1,2})[:hH](\d{0,2})', parts[1].strip())
                if ot_parts and ct_parts:
                    p_start = int(ot_parts[0][0]) * 60 + int(ot_parts[0][1] or 0)
                    p_end = int(ct_parts[0][0]) * 60 + int(ct_parts[0][1] or 0)
                    overlap_start = max(arr_min, p_start)
                    overlap_end = min(dep_min, p_end)
                    if overlap_end - overlap_start >= 15:
                        return True, w.strip()
    except Exception:
        pass
    return False, ""

@app.post("/api/ai-itinerary")
def generate_itinerary(req: ItineraryRequest, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    all_places = get_all_places(include_hidden=False)
    if not all_places:
        raise HTTPException(status_code=500, detail="Cơ sở dữ liệu đang rỗng.")

    num_stops = req.num_stops if (req.num_stops and 2 <= req.num_stops <= 4) else 3
    radius_km = float(req.radius_km) if (req.radius_km and float(req.radius_km) > 0) else None

    # 1. RÀNG BUỘC NGHIỆP VỤ BẮT BUỘC (BUSINESS RULE 3 & KIỂM THỬ BẮT BUỘC)
    free_duration = parse_free_time_minutes(req.free_time)
    target_budget = parse_target_budget_amount(req)
    if target_budget == 0 or req.budget == "free" or req.budget_level == "free":
        target_budget = 0
        req.budget_level = "free"

    # Ràng buộc thời gian rảnh thực tế theo số trạm:
    # 2 trạm cần tối thiểu 70 phút (2 chặng xe máy ~20p + 2 trạm x 25p)
    # 3 trạm cần tối thiểu 105 phút (3 chặng xe máy ~30p + 3 trạm x 25p)
    # 4 trạm cần tối thiểu 140 phút (4 chặng xe máy ~40p + 4 trạm x 25p)
    min_time_needed = {2: 70, 3: 105, 4: 140}.get(num_stops, 105)
    if free_duration < min_time_needed:
        h_free = free_duration // 60
        m_free = free_duration % 60
        free_display = f"{h_free}h{m_free:02d}p" if h_free > 0 else f"{m_free} phút"
        h_need = min_time_needed // 60
        m_need = min_time_needed % 60
        need_display = f"{h_need}h{m_need:02d}p" if m_need > 0 else f"{h_need} tiếng"
        return {
            "feasible": False,
            "error_code": "TIME_TOO_SHORT",
            "message": f"Khung giờ rảnh của bạn ({free_display} - {free_duration} phút) quá ngắn để hoàn thành lịch trình {num_stops} trạm (tối thiểu cần khoảng {need_display} bao gồm thời gian di chuyển và dừng chân trải nghiệm).",
            "suggestion": f"Bạn hãy mở rộng khung giờ rảnh lên tối thiểu {need_display} (hoặc gợi ý: 14:00 - 18:30) hoặc chọn số trạm ít hơn để trải nghiệm không bị vội nhé!",
            "recommended_time": "14:00 - 18:30",
            "recommended_budget": target_budget
        }

    # Ràng buộc ngân sách: Nếu đi ăn uống mà ngân sách < 40k (không phải chọn 0đ)
    if req.purpose in ["an_uong", "ca_hai"] and req.budget_level != "free" and target_budget < 40000:
        return {
            "feasible": False,
            "error_code": "BUDGET_TOO_LOW",
            "message": f"Ngân sách ({target_budget:,}đ) quá thấp cho lộ trình ẩm thực 3 trạm tại TP.HCM.",
            "suggestion": "Bạn hãy nới ngân sách lên tối thiểu 80.000đ - 100.000đ hoặc chuyển sang mục đích 'Chỉ đi Tham quan' để check-in các điểm 0đ nhé!",
            "recommended_time": req.free_time,
            "recommended_budget": 100000
        }

    # 1. Xác định toạ độ điểm xuất phát (Ưu tiên GPS chính xác từ Geolocation API của trình duyệt)
    if req.start_lat and req.start_lon:
        start_lat, start_lon = float(req.start_lat), float(req.start_lon)
    else:
        start_lat, start_lon = resolve_start_coords(req.start_location)

    # Ràng buộc giờ mở cửa (Business Rule 2 & 3): Địa điểm đóng cửa KHÔNG ĐƯỢC đưa vào lịch trình
    open_pool = [p for p in all_places if is_place_open_during_window(p, req.free_time)]

    # Lọc theo bán kính nếu có thiết lập
    if radius_km:
        in_radius_pool = [
            p for p in open_pool 
            if p.get("lat") and p.get("lon") and 
            calculate_haversine_distance(start_lat, start_lon, float(p["lat"]), float(p["lon"])) <= radius_km
        ]
        if len(in_radius_pool) >= num_stops:
            open_pool = in_radius_pool
    
    # Kiểm tra số lượng quán mở cửa theo mục đích
    if req.purpose == "an_uong":
        open_purpose_places = [p for p in open_pool if p.get("category") == "an_uong"]
    elif req.purpose == "di_choi":
