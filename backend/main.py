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
        open_purpose_places = [p for p in open_pool if p.get("category") == "di_choi"]
    else:
        open_purpose_places = open_pool

    if len(open_purpose_places) < num_stops:
        return {
            "feasible": False,
            "error_code": "ALL_PLACES_CLOSED",
            "message": f"Vào khung giờ rảnh '{req.free_time}', hầu như tất cả các địa điểm thuộc mục đích này đều đã đóng cửa (chỉ có {len(open_purpose_places)} điểm mở cửa).",
            "suggestion": "Bạn hãy đổi sang khung giờ rảnh vào ban ngày hoặc buổi tối (ví dụ: '18:30 - 22:30' hoặc '14:00 - 18:30') để khám phá trọn vẹn nhé!",
            "recommended_time": "18:30 - 22:30",
            "recommended_budget": target_budget
        }

    available_places = open_pool
    places_by_id = {p["id"]: p for p in available_places}

    companion_map = {
        "di_1_minh": "Đi một mình (Solo)",
        "nguoi_yeu": "Cặp đôi / Người yêu (Hẹn hò lãng mạn)",
        "ban_be": "Nhóm bạn thân",
        "gia_dinh": "Gia đình (Có người lớn / trẻ em)"
    }
    companion_str = companion_map.get(req.companion or "ban_be", "Nhóm bạn thân")

    purpose_map = {
        "an_uong": "Chỉ đi Ăn uống (Thưởng thức ẩm thực đặc sản)",
        "di_choi": "Chỉ đi Vui chơi (Tham quan di tích, check-in, chụp ảnh, cà phê - TUYỆT ĐỐI KHÔNG ăn no)",
        "ca_hai": "Cả hai (Kết hợp vừa ăn đặc sản vừa tham quan/vui chơi/cafe)"
    }
    purpose_str = purpose_map.get(req.purpose or "ca_hai", "Cả hai (Ăn uống và Vui chơi)")
    takenote_str = req.takenote or req.context or "Không có ghi chú loại trừ đặc biệt."

    # 2. Chấm điểm Smart Score & Chọn Top 20 ứng viên sáng giá nhất (Phân tầng 2-Tier + Bán kính/Cự ly + Đánh giá)
    mapped_comp_tag = {"ban_be": "nhom_ban", "nguoi_yeu": "hen_ho", "gia_dinh": "gia_dinh", "di_1_minh": "di_1_minh"}.get(req.companion, "nhom_ban")
    scored_candidates = []
    for p in open_purpose_places:
        c_score = 0.0
        # 1. Điểm phân tầng đồng hành 2-Tier
        tier_pts, _ = get_companion_tier_score(p, mapped_comp_tag)
        c_score += tier_pts

        # 2. Điểm cự ly gần điểm xuất phát
        p_lat = float(p.get("lat") or start_lat)
        p_lon = float(p.get("lon") or start_lon)
        dist_from_start = calculate_haversine_distance(start_lat, start_lon, p_lat, p_lon)
        if dist_from_start <= 3.0:
            c_score += 25.0 - (dist_from_start / 3.0) * 5.0
        elif dist_from_start <= 7.0:
            c_score += 20.0 - ((dist_from_start - 3.0) / 4.0) * 8.0
        else:
            c_score += max(0.0, 12.0 - (dist_from_start - 7.0))

        # 3. Điểm đánh giá sao & lượt review
        rating = float(p.get("rating", 4.0))
        reviews_count = int(p.get("reviews_count", 0))
        c_score += (rating - 4.0) * 4.0 + math.log10(reviews_count + 1) * 2.0

        scored_candidates.append((c_score, p))

    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    if req.purpose == "ca_hai":
        play_cands = [item[1] for item in scored_candidates if item[1].get("category") == "di_choi"]
        eat_cands = [item[1] for item in scored_candidates if item[1].get("category") == "an_uong"]
        if play_cands and eat_cands:
            # Top 10 vui chơi + Top 10 ăn uống để đảm bảo Gemini có cả hai thể loại để lựa chọn
            top_candidates = play_cands[:10] + eat_cands[:10]
        else:
            top_candidates = [item[1] for item in scored_candidates[:20]]
    else:
        top_candidates = [item[1] for item in scored_candidates[:20]]

    if len(top_candidates) < num_stops:
        top_candidates = open_purpose_places[:20]

    # Tạo tóm tắt Top 20 quán để đưa vào Gemini AI (Kèm đầy đủ bình luận Khen / Chê thực tế)
    places_lines = []
    for p in top_candidates:
        cat = "Ẩm thực" if p.get("category") == "an_uong" else "Đi chơi/Di tích"
        best_c = (p.get("best_review") or "").replace("\n", " ").strip()
        worst_c = (p.get("worst_review") or "").replace("\n", " ").strip()
        if len(best_c) > 130:
            best_c = best_c[:130] + "..."
        if len(worst_c) > 100:
            worst_c = worst_c[:100] + "..."
        price_str = f"{p.get('min_price', 0):,}đ - {p.get('max_price', 0):,}đ"
        peak_str = (p.get("peak_hours") or "").strip()
        info = f"ID {p['id']}: {p['name']} | Thể loại: {cat} | Giá: {price_str} | Giờ mở: {p.get('open_time')}-{p.get('close_time')} | Đánh giá: {p.get('rating')}⭐ ({p.get('reviews_count', 0)} đánh giá)"
        if peak_str:
            info += f" | Giờ cao điểm quán: {peak_str}"
        if best_c:
            info += f" | Khách khen/Món ngon: \"{best_c}\""
        if worst_c:
            info += f" | Khách chê/Lưu ý: \"{worst_c}\""
        places_lines.append(info)
    places_context = "\n".join(places_lines)

    selected_ids = []
    overall_advice = ""
    gemini_stops_info = {}
    model_choice = req.ai_model or "gemini-3.5-flash-lite"
    actual_model = model_choice
    ai_status = "fallback"

    # 3. Sử dụng Google Gemini AI để thấu hiểu ngữ cảnh và chọn các trạm phù hợp nhất (ưu tiên gemini-3.5-flash-lite siêu nhanh)
    if ai_client and req.ai_model not in ["none", "rule_based", "off"]:
        prompt = f"""Bạn là Chuyên gia Lập Lộ trình Du lịch & Ẩm thực Sài Gòn (TP.HCM) cho nền tảng SGGo! Travel Guide.
YÊU CẦU CỦA NGƯỜI DÙNG:
- Điểm xuất phát: "{req.start_location}"
- Khung giờ rảnh: "{req.free_time}"
- Bạn đồng hành: "{companion_str}"
- Mục đích chuyến đi: "{purpose_str}"
- Số lượng trạm dừng mong muốn: {num_stops} trạm
- Ngân sách tối đa mong muốn: {target_budget:,}đ (Nếu là 0đ nghĩa là miễn phí)
- Ghi chú & Yêu cầu riêng (Take note): "{takenote_str}"

TOP ĐỊA ĐIỂM SÁNG GIÁ NHẤT ĐÃ ĐƯỢC HỆ THỐNG LỌC SẴN:
{places_context}

QUY TẮC BẮT BUỘC KHI LẬP LỘ TRÌNH:
1. MỤC ĐÍCH CHUYẾN ĐI (BẮT BUỘC TUÂN THỦ TÙY THEO LỰA CHỌN CỦA NGƯỜI DÙNG: "{purpose_str}"):
   - Nếu là "Chỉ đi Ăn uống" (purpose="an_uong"): 100% TẤT CẢ CÁC TRẠM PHẢI LÀ quán ăn/ẩm thực (category='an_uong')! TUYỆT ĐỐI KHÔNG chọn điểm di tích hay bảo tàng!
   - Nếu là "Chỉ đi Vui chơi" (purpose="di_choi"): 100% TẤT CẢ CÁC TRẠM PHẢI LÀ điểm tham quan, di tích, vui chơi, workshop (category='di_choi')! TUYỆT ĐỐI KHÔNG chọn quán ăn uống!
   - CHỈ KHI NÀO người dùng chọn "Cả hai" (purpose="ca_hai"): MỚI BẮT BUỘC kết hợp cả hai thể loại:
     + Nếu chọn {num_stops} = 2: BẮT BUỘC chọn đúng 1 điểm Đi chơi/Di tích VÀ 1 quán Ẩm thực! TUYỆT ĐỐI KHÔNG chọn 2 quán ăn hoặc 2 điểm đi chơi!
     + Nếu chọn {num_stops} = 3: BẮT BUỘC có ít nhất 1 điểm Đi chơi/Di tích VÀ ít nhất 1 quán Ẩm thực (ví dụ 1 chơi + 2 ăn, hoặc 2 chơi + 1 ăn)!
     + Nếu chọn {num_stops} = 4: BẮT BUỘC có ít nhất 1 điểm Đi chơi/Di tích VÀ ít nhất 1 quán Ẩm thực!
2. BẠN ĐỒNG HÀNH:
   - Ưu tiên không gian phù hợp với "{companion_str}".
3. XỬ LÝ GHI CHÚ ĐẶC BIỆT (TAKE NOTE) & LOẠI TRỪ NGỮ NGHĨA (QUAN TRỌNG):
   - Đọc kỹ ghi chú của người dùng: "{takenote_str}"
   - Nếu người dùng ghi "chán chỗ X", "loại trừ X", "không thích X", "tránh X" (tên quán hoặc thương hiệu) -> TUYỆT ĐỐI LOẠI BỎ địa điểm đó, không được chọn!
   - Nếu người dùng ghi kiêng cữ / dị ứng / không muốn ăn món gì (ví dụ: "không ăn cay", "dị ứng hải sản", "ghét ốc", "không đồ ngọt", "thèm nướng", "ăn chay"...) -> Đọc kỹ tên quán, món ăn đặc trưng và review khen/chê ở trên để LOẠI TRỪ triệt để quán có món đó, và ưu tiên quán đúng sở thích!
   - Nếu người dùng có yêu cầu về không gian (ví dụ: "thích máy lạnh", "yên tĩnh làm việc", "ngoài trời thoáng mát", "bãi xe rộng", "không ồn ào"...) -> Đối chiếu trực tiếp với bình luận của khách để chọn quán phù hợp.
4. NGUYÊN TẮC VIẾT `must_try_tip` (CHẤT LƯỢNG CAO, SỰ THẬT TỪ REVIEW, CẤM ẢO DỮ LIỆU):
   - NẾU LÀ QUÁN ĂN UỐNG (category='an_uong'):
     BẮT BUỘC TRÍCH XUẤT ĐÍCH DANH TÊN MÓN ĂN / ĐỒ UỐNG ĐƯỢC KHEN NHIỀU NHẤT từ mục "Khách khen/Món ngon" của quán ở trên.
     Nếu trong review của quán không nhắc đến món cụ thể, ghi đúng: "Không có đề xuất món cụ thể trong đánh giá thực tế."
     TUYỆT ĐỐI CẤM BỊA ĐẶT TÊN MÓN KHÔNG CÓ TRONG DỮ LIỆU!
   - NẾU LÀ ĐIỂM ĐI CHƠI / DI TÍCH (category='di_choi'):
     BẮT BUỘC GHI RÕ VIỆC NÊN LÀM HOẶC HOẠT ĐỘNG NỔI BẬT NHẤT KHI ĐẾN ĐÂY (ví dụ: ngắm cảnh/chụp ảnh góc đẹp, tham quan triển lãm, trải nghiệm hoạt động...).
   - TUYỆT ĐỐI CẤM các câu hiển nhiên, ngô nghê hoặc rao giảng vô ích như: "tự lấy muỗng đũa", "ăn vừa bụng", "nhớ giữ gìn vệ sinh", "uống nhiều nước"!
5. NGUYÊN TẮC TRÌNH BÀY `overall_advice` (TÁCH BẠCH TỪNG TRẠM, NÓI THẲNG TRỌNG TÂM, TUYỆT ĐỐI KHÔNG NGÔ NGHÊ):
   BẮT BUỘC định dạng xuống dòng mạch lạc theo đúng mẫu sau:
   Tiếp nhận tiêu chí:
   • Khung giờ: {req.free_time} | Bạn đồng hành: {companion_str}
   • Ghi chú riêng (Take note): "{takenote_str}" (Nếu có ghi chú, trích dẫn chính xác yêu cầu của người dùng; nếu trống thì ghi "Không có ghi chú riêng")

   Lý do lựa chọn lộ trình:
   • Vì sao chọn [Tên trạm 1]: [Nêu lý do đắt giá và cụ thể: không gian, phong cách, vibe hợp với {companion_str} ra sao và đáp ứng take note thế nào]
   • Vì sao chọn [Tên trạm 2]: [Nêu lý do đắt giá và cụ thể về quán/điểm này]
   (Nếu có trạm 3, 4 thì tiếp tục: • Vì sao chọn [Tên trạm X]: ...)
   • Logic kết hợp lộ trình: [Giải thích logic dòng chảy trải nghiệm (flow): tại sao đi trạm này trước rồi sang trạm kia sau; sự chuyển tiếp nhịp điệu từ hoạt động này sang hoạt động kia tự nhiên thế nào; tiện đường xe máy mà không bị ngược hướng]

   CÁC ĐIỀU CẤM KỴ KHI VIẾT `overall_advice`:
   1. TUYỆT ĐỐI KHÔNG LẶP LẠI CHI PHÍ & THỜI LƯỢNG RẢNH (CẤM các câu như "chi phí tiết kiệm dưới Xđ", "hoàn toàn phù hợp ngân sách và thời lượng rảnh..."). Giao diện đã có bảng đo lường KPI riêng, không nhại lại!
   2. TUYỆT ĐỐI KHÔNG DÙNG CÂU KHẨU HIỆU SÁO RỖNG, QUẢNG CÁO NGÔ NGHÊ như: "kết hợp hoàn hảo", "cực kỳ tiết kiệm", "văn hóa tâm linh về đêm", "thỏa mãn tuyệt đối", "hứa hẹn mang lại". Hãy dùng văn phong am hiểu, tự nhiên, sắc sảo của một người bạn Sài Gòn thực thụ!
   3. KẾT THÚC NGAY SAU DÒNG '• Logic kết hợp lộ trình'. TUYỆT ĐỐI KHÔNG thêm bất kỳ mục nào khác như 'Cân đối chi phí', 'Chi phí' hay 'Thời lượng'.
6. RÀNG BUỘC NGÂN SÁCH: Tổng chi phí ước tính các trạm PHẢI NẰM TRONG ngân sách {target_budget:,}đ.
7. Chọn chính xác {num_stops} địa điểm từ danh sách trên theo thứ tự hợp lý và chia khung giờ cụ thể nằm trọn trong "{req.free_time}".
8. Trả về ĐÚNG định dạng JSON sau (không dùng bất kỳ chữ nào ngoài JSON):
{{
  "selected_ids": [{", ".join(f"id{i+1}" for i in range(num_stops))}],
  "overall_advice": "Văn bản phân tích lộ trình trình bày xuống dòng mạch lạc như hướng dẫn ở mục 5",
  "stops": [
    {{
      "place_id": id1,
      "time_slot": "hh:mm - hh:mm",
      "action_title": "Tiêu đề chặng ngắn gọn",
      "recommended_dwell_min": 60,
      "must_try_tip": "Món ăn ruột trích xuất thật từ review (nếu là quán ăn) hoặc việc nên làm (nếu là điểm đi chơi)"
    }}
  ]
}}
"""
        models_to_try = [model_choice] + [m for m in ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"] if m != model_choice]
        for model_name in models_to_try:
            try:
                res = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                if res and res.text:
                    raw_text = res.text.strip()
                    clean_json = raw_text
                    if "```json" in clean_json:
                        clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                    elif "```" in clean_json:
                        clean_json = clean_json.split("```")[1].split("```")[0].strip()
                    
                    parsed = json.loads(clean_json)
                    s_ids = parsed.get("selected_ids", [])
                    if len(s_ids) >= num_stops and all(pid in places_by_id for pid in s_ids[:num_stops]) and len(set(s_ids[:num_stops])) == num_stops:
                        chosen_cats = [places_by_id[pid].get("category") for pid in s_ids[:num_stops]]
                        if req.purpose == "an_uong" and any(c != "an_uong" for c in chosen_cats):
                            continue
                        elif req.purpose == "di_choi" and any(c != "di_choi" for c in chosen_cats):
                            continue
                        elif req.purpose == "ca_hai" and ("an_uong" not in chosen_cats or "di_choi" not in chosen_cats):
                            continue
                        selected_ids = s_ids[:num_stops]
                        overall_advice = parsed.get("overall_advice", "")
                        for st in parsed.get("stops", []):
                            gemini_stops_info[st.get("place_id")] = st
                        actual_model = model_name
                        ai_status = "success"
                        break
            except Exception:
                continue

    # 4. Fallback phòng hộ nếu Gemini AI không kết nối được hoặc dùng Rule-Based Heuristic
    if len(selected_ids) < num_stops:
        ai_status = "fallback"
        actual_model = "rule_based"
        candidates = list(open_purpose_places)

        # Lọc theo ngân sách (G6-FR05 MUST): Đảm bảo các trạm không có giá vượt quá ngân sách
        if req.budget_level == "free" or target_budget == 0:
            free_cands = [p for p in candidates if (p.get("min_price") or 0) == 0 and (p.get("max_price") or 0) == 0]
            if len(free_cands) >= num_stops:
                candidates = free_cands
        elif target_budget > 0:
            max_single_cost = int(target_budget * 0.65)
            budget_filtered = [
                p for p in candidates 
                if (p.get("min_price") or 0) <= max_single_cost or ((p.get("min_price") or 0) == 0 and (p.get("max_price") or 0) == 0)
            ]
            if len(budget_filtered) >= num_stops:
                candidates = budget_filtered

        # Xáo trộn danh sách ứng viên theo shuffle_seed (G6-FR06: Xáo trộn/Đổi phương án khác)
        if req.shuffle_seed and req.shuffle_seed > 0:
            shift = (req.shuffle_seed * 4) % max(1, len(candidates))
            candidates = candidates[shift:] + candidates[:shift]

        # Lọc loại trừ theo Take note
        if req.takenote:
            tn_clean = remove_accent(req.takenote).lower()
            filtered_cands = []
            for p in candidates:
                raw_name = p.get("name", "")
                base_name = raw_name.split("(")[0].strip()
                norm_full = remove_accent(raw_name).lower()
                norm_base = remove_accent(base_name).lower()

                is_excluded = False
                if (norm_base and norm_base in tn_clean) or (norm_full and norm_full in tn_clean):
                    is_excluded = True
                else:
                    words = [w for w in norm_base.split() if len(w) > 1]
                    for i in range(len(words) - 1):
                        bigram = f"{words[i]} {words[i+1]}"
                        if bigram in tn_clean and bigram not in ["quan 5", "tp hcm", "sai gon", "duong an", "hoi quan", "thanh pho"]:
                            is_excluded = True
                            break

                if not is_excluded:
                    filtered_cands.append(p)

            if len(filtered_cands) >= num_stops:
                candidates = filtered_cands

        seed = req.shuffle_seed or 0

        # Đối với mục đích 'Cả hai': BẮT BUỘC kết hợp cả vui chơi (di_choi) và ăn uống (an_uong) cho mọi số trạm (2, 3, 4)
        if req.purpose == "ca_hai":
            play_cands = [p for p in candidates if p.get("category") == "di_choi"]
            eat_cands = [p for p in candidates if p.get("category") == "an_uong"]
            if play_cands and eat_cands:
                play_sorted = sorted(play_cands, key=lambda p: calculate_haversine_distance(start_lat, start_lon, p.get("lat") or 10.75, p.get("lon") or 106.66))
                eat_sorted = sorted(eat_cands, key=lambda p: calculate_haversine_distance(start_lat, start_lon, p.get("lat") or 10.75, p.get("lon") or 106.66))
                
                off_play = (seed * 2) % max(1, len(play_sorted) - 2) if len(play_sorted) > 3 else 0
                off_eat = (seed * 3) % max(1, len(eat_sorted) - 3) if len(eat_sorted) > 4 else 0
                
                win_play = play_sorted[off_play:off_play + 6]
                win_eat = eat_sorted[off_eat:off_eat + 8]
                
                if num_stops == 2:
                    # 1 Đi chơi + 1 Ăn uống
                    opt_play = optimize_route_nearest_neighbor((start_lat, start_lon), win_play, max_stops=1)
                    opt_eat = optimize_route_nearest_neighbor((start_lat, start_lon), win_eat, max_stops=1)
                    opt_stops = optimize_route_nearest_neighbor((start_lat, start_lon), opt_play + opt_eat, max_stops=2)
                elif num_stops == 4:
                    # 2 Đi chơi + 2 Ăn uống
                    opt_play = optimize_route_nearest_neighbor((start_lat, start_lon), win_play, max_stops=2)
                    opt_eat = optimize_route_nearest_neighbor((start_lat, start_lon), win_eat, max_stops=2)
                    opt_stops = optimize_route_nearest_neighbor((start_lat, start_lon), opt_play + opt_eat, max_stops=4)
                else:
                    # num_stops == 3: 1 Đi chơi + 2 Ăn uống
                    best_combo = None
                    best_dist = float('inf')

                    import itertools
                    for p_stop in win_play[:4]:
                        p_cost = p_stop.get("min_price", 0)
                        rem_budget = target_budget - p_cost if target_budget > 0 else 999999999
                        for e1, e2 in itertools.combinations(win_eat[:8], 2):
                            if (e1.get("min_price", 0) + e2.get("min_price", 0)) <= rem_budget:
                                trip = [p_stop, e1, e2]
                                ordered = optimize_route_nearest_neighbor((start_lat, start_lon), trip, max_stops=3)
                                d = calculate_haversine_distance(start_lat, start_lon, ordered[0].get("lat") or 10.75, ordered[0].get("lon") or 106.66) + \
                                    calculate_haversine_distance(ordered[0].get("lat") or 10.75, ordered[0].get("lon") or 106.66, ordered[1].get("lat") or 10.75, ordered[1].get("lon") or 106.66) + \
                                    calculate_haversine_distance(ordered[1].get("lat") or 10.75, ordered[1].get("lon") or 106.66, ordered[2].get("lat") or 10.75, ordered[2].get("lon") or 106.66)
                                if d < best_dist:
                                    best_dist = d
                                    best_combo = ordered

                    if best_combo:
                        opt_stops = best_combo
                    else:
                        opt_play = optimize_route_nearest_neighbor((start_lat, start_lon), win_play, max_stops=1)
                        opt_eat = optimize_route_nearest_neighbor((start_lat, start_lon), win_eat, max_stops=2)
                        opt_stops = optimize_route_nearest_neighbor((start_lat, start_lon), opt_play + opt_eat, max_stops=3)
            else:
                c_sorted = sorted(candidates, key=lambda p: calculate_haversine_distance(start_lat, start_lon, p.get("lat") or 10.75, p.get("lon") or 106.66))
                off = (seed * 3) % max(1, len(c_sorted) - 4) if len(c_sorted) > 5 else 0
                opt_stops = optimize_route_nearest_neighbor((start_lat, start_lon), c_sorted[off:off + 10], max_stops=num_stops)
        else:
            c_sorted = sorted(candidates, key=lambda p: calculate_haversine_distance(start_lat, start_lon, p.get("lat") or 10.75, p.get("lon") or 106.66))
            off = (seed * 3) % max(1, len(c_sorted) - 4) if len(c_sorted) > 5 else 0
            opt_stops = find_budget_optimal_route((start_lat, start_lon), c_sorted[off:off + 12], target_budget=target_budget, max_stops=num_stops)

        selected_ids = [p["id"] for p in opt_stops]
        takenote_txt = f'"{takenote_str}"' if (takenote_str and takenote_str != "Không có ghi chú riêng") else 'Không có ghi chú riêng'
        stop_reasons = []
        for idx, p in enumerate(opt_stops):
            cat_label = "ẩm thực" if p.get("category") == "an_uong" else "đi chơi / tham quan"
            stop_reasons.append(f"• Vì sao chọn {p.get('name')}: Điểm {cat_label} chuẩn gu, không gian phù hợp với {companion_str} và thuận tiện giờ mở cửa.")
        stop_reasons_str = "\n".join(stop_reasons)
        overall_advice = (
            f"Tiếp nhận tiêu chí:\n"
            f"• Khung giờ: {req.free_time} | Bạn đồng hành: {companion_str}\n"
            f"• Ghi chú riêng (Take note): {takenote_txt}\n\n"
            f"Lý do lựa chọn lộ trình:\n"
            f"{stop_reasons_str}\n"
            f"• Logic kết hợp lộ trình: Tuyến đường {num_stops} chặng được sắp xếp tối ưu theo cung đường từ '{req.start_location}', chuyển tiếp tự nhiên giữa các hoạt động mà không bị ngược hướng di chuyển."
        )

    chosen_places = [places_by_id[pid] for pid in selected_ids if pid in places_by_id]
    if len(chosen_places) < num_stops:
        chosen_places = open_purpose_places[:num_stops]

    # 5. SẮP XẾP TỐI ƯU CHỐNG NGƯỢC ĐƯỜNG (Nearest Neighbor TSP từ vị trí xuất phát)
    optimized_places = optimize_route_nearest_neighbor((start_lat, start_lon), chosen_places, max_stops=num_stops)
    if not optimized_places:
        optimized_places = chosen_places

    # 6. Tạo đường link Google Maps Multi-stop dẫn đường xe máy liên hoàn
    lat0, lon0 = start_lat, start_lon
    dest_p = optimized_places[-1]
    if len(optimized_places) > 1:
        waypoints_str = "|".join(f"{p['lat']},{p['lon']}" for p in optimized_places[:-1])
        gmaps_multi_url = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={lat0},{lon0}"
            f"&destination={dest_p['lat']},{dest_p['lon']}"
            f"&waypoints={waypoints_str}"
            f"&travelmode=two_wheeler"
        )
    else:
        gmaps_multi_url = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={lat0},{lon0}"
            f"&destination={dest_p['lat']},{dest_p['lon']}"
            f"&travelmode=two_wheeler"
        )

    # 7. Xây dựng dữ liệu Timeline chi tiết & Phân bổ thời gian thực tế (Thời gian chạy xe biến thiên theo giờ cao điểm + Dừng chân theo quỹ thời gian)
    time_matches = re.findall(r'(\d{1,2})[:hH](\d{0,2})', req.free_time)
    if time_matches:
        clock_cursor = int(time_matches[0][0]) * 60 + int(time_matches[0][1] or 0)
    else:
        clock_cursor = 14 * 60

    # Bước 7.1: Định tuyến OSRM / Haversine chuẩn & Tính thời gian biến thiên theo giao thông TP.HCM
    all_stop_coords = [(start_lat, start_lon)] + [(float(p.get("lat") or start_lat), float(p.get("lon") or start_lon)) for p in optimized_places]
    osrm_legs = get_osrm_route_legs(all_stop_coords)
    is_osrm_active = bool(osrm_legs and len(osrm_legs) == len(optimized_places))
    routing_source = "osrm" if is_osrm_active else "haversine"
    routing_warning = None
    if not is_osrm_active:
        routing_warning = "Không thể kết nối máy chủ định tuyến đường phố OpenStreetMap (OSRM). Hệ thống đã tự động chuyển sang đo khoảng cách Haversine chuẩn trắc địa."

    temp_cursor = clock_cursor
    travel_data = []
    curr_lat, curr_lon = start_lat, start_lon
    total_dist = 0.0
    total_t_min = 0

    for idx, spot in enumerate(optimized_places):
        p_lat = float(spot.get("lat") or curr_lat)
        p_lon = float(spot.get("lon") or curr_lon)
        if is_osrm_active:
            dist = osrm_legs[idx]
        else:
            raw_h_dist = calculate_haversine_distance(curr_lat, curr_lon, p_lat, p_lon)
            dist = round(raw_h_dist, 2)  # Haversine chuẩn thuần túy, tuyệt đối KHÔNG nhân 1.25
        t_min, traf_note, traf_badge = calculate_traffic_speed_model(dist, temp_cursor)
        travel_data.append((dist, t_min, traf_note, traf_badge))
        total_dist += dist
        total_t_min += t_min
        curr_lat, curr_lon = p_lat, p_lon
        temp_cursor += t_min + 45

    # Bước 7.2: Mô hình Dừng Chân Lai Theo Đúng 7 Nhóm Trải Nghiệm Học Thuật (Hybrid Dwell Model A + B)
    proportional_dwells = []
    dwell_group_labels = []
    for spot in optimized_places:
        ai_info = gemini_stops_info.get(spot["id"], {})
        rec_dwell = ai_info.get("recommended_dwell_min")
        min_d, def_d, max_d, grp_label = get_natural_dwell_bounds(spot)
        if isinstance(rec_dwell, (int, float)) and rec_dwell > 0:
            dwell = max(min_d, min(max_d, int(rec_dwell)))
        else:
            dwell = def_d
        # Bổ sung 10 phút đệm thực tế (tìm chỗ gửi xe, lấy vé, gọi món)
        dwell += 10
        proportional_dwells.append(dwell)
        dwell_group_labels.append(grp_label)

    # Kiểm tra quỹ thời gian: Cân đối co giãn thời gian dừng chân để tổng thời gian (di chuyển + dừng chân) vừa vặn khung giờ rảnh
    stay_budget = max(len(optimized_places) * 20, free_duration - total_t_min)
    current_total_dwell = sum(proportional_dwells)
    if current_total_dwell > stay_budget:
        scale_factor = stay_budget / current_total_dwell
        scaled_dwells = []
        for d, spot in zip(proportional_dwells, optimized_places):
            min_d, _, _, _ = get_natural_dwell_bounds(spot)
            # Cân đối co giãn, tối thiểu 20 phút cho mỗi trạm
            scaled_d = max(20, min(d, int(round(d * scale_factor))))
            scaled_dwells.append(scaled_d)
        
        # Cân đối tinh chỉnh để tổng thời gian dừng + di chuyển vừa vặn với free_duration
        while sum(scaled_dwells) > stay_budget and any(d > 20 for d in scaled_dwells):
            max_idx = max(range(len(scaled_dwells)), key=lambda i: scaled_dwells[i])
            if scaled_dwells[max_idx] > 20:
                scaled_dwells[max_idx] -= 5
            else:
                break
        proportional_dwells = scaled_dwells

    steps = []
    stops_db_data = []
    curr_lat, curr_lon = start_lat, start_lon

    for idx, spot in enumerate(optimized_places):
        p_lat = float(spot.get("lat") or curr_lat)
        p_lon = float(spot.get("lon") or curr_lon)
        dist, t_min, traf_note, traf_badge = travel_data[idx]
        dwell_min = proportional_dwells[idx]

        arrive_min = clock_cursor + t_min
        depart_min = arrive_min + dwell_min
        clock_cursor = depart_min

        arr_h, arr_m = (arrive_min // 60) % 24, arrive_min % 60
        dep_h, dep_m = (depart_min // 60) % 24, depart_min % 60
        slot_time = f"{arr_h:02d}:{arr_m:02d} - {dep_h:02d}:{dep_m:02d}"

        ai_info = gemini_stops_info.get(spot["id"], {})
        action_title = ai_info.get("action_title") or f"Trạm {idx+1}: Khám phá {spot['name']} [{ 'Ẩm thực' if spot.get('category') == 'an_uong' else 'Đi chơi/Di tích' }]"
        ai_reason = ai_info.get("ai_reason", "Địa điểm mở cửa phù hợp, thuận tuyến đường di chuyển tối ưu.")
        must_try_tip = ai_info.get("must_try_tip")
        if not must_try_tip or not must_try_tip.strip():
            if spot.get("category") == "an_uong":
                must_try_tip = spot.get("must_try_dishes") or (f"Món nổi bật: {spot.get('best_review')[:70]}..." if spot.get("best_review") else "Không có đề xuất món cụ thể trong đánh giá thực tế.")
            else:
                must_try_tip = "Tham quan không gian kiến trúc, chụp ảnh check-in và khám phá các trải nghiệm tại điểm đến."

        traffic_warning = f"[{traf_badge}] {traf_note} • Khoảng cách ~{dist} km ({t_min} phút xe máy)."

        p_min_cost = spot.get("min_price", 0)
        p_max_cost = spot.get("max_price", 0)

        # Xây dựng giải thích rule minh bạch (G6-FR10 SHOULD)
        tier_pts, fit_tier = get_companion_tier_score(spot, mapped_comp_tag)
        rule_reasons = []
        if tier_pts > 0:
            rule_reasons.append(f"Khớp bối cảnh '{companion_str}' (+{int(tier_pts)}đ Tier {fit_tier})")
        rule_reasons.append(f"Mở cửa ({spot.get('open_time')}-{spot.get('close_time')})")
        avg_cost = (p_min_cost + p_max_cost) // 2
        rule_reasons.append(f"Chi phí ~{avg_cost:,}đ")
        rule_reasons.append(f"Dừng chân ~{dwell_min} phút (cân đối quỹ giờ rảnh)")
        rule_explanation = " • ".join(rule_reasons)

        spot_peak = spot.get("peak_hours") or ""
        is_peak, peak_win = check_peak_hours_overlap(arrive_min, depart_min, spot_peak)
        if is_peak:
            peak_warning = f"⚡ Trùng giờ cao điểm ({peak_win}): Dự kiến quán rất đông khách vào khung giờ này, bạn nên chủ động đặt bàn trước hoặc ghé sớm!"
        elif spot_peak:
            peak_warning = f"Quán có giờ cao điểm ({spot_peak}). Khung giờ bạn ghé ({arr_h:02d}:{arr_m:02d} - {dep_h:02d}:{dep_m:02d}) không trùng giờ cao điểm, không gian tương đối thoáng đãng để bạn yên tâm trải nghiệm."
        else:
            peak_warning = f"Khung giờ bạn ghé ({arr_h:02d}:{arr_m:02d} - {dep_h:02d}:{dep_m:02d}) không ghi nhận giờ cao điểm căng thẳng, quán thoáng đãng bạn hoàn toàn yên tâm trải nghiệm."

        step_dict = {
            "place_id": spot.get("id"),
            "id": spot.get("id"),
            "name": spot.get("name"),
            "category": spot.get("category"),
            "address": spot.get("address"),
            "district": spot.get("district"),
            "rating": spot.get("rating"),
            "reviews_count": spot.get("reviews_count"),
            "google_maps_url": spot.get("google_maps_url"),
            "min_price": p_min_cost,
            "max_price": p_max_cost,
            "open_time": spot.get("open_time"),
            "close_time": spot.get("close_time"),
            "time": slot_time,
            "action": action_title,
            "location": f"{spot['name']} — {spot.get('address')} ⭐ {spot.get('rating')}".strip(),
            "travel_info": f"Di chuyển ~{dist} km (~{t_min} phút xe máy, dừng ~{dwell_min} phút)",
            "traffic_warning": traffic_warning,
            "peak_hours": spot_peak,
            "is_peak_hour": is_peak,
            "peak_warning": peak_warning,
            "ai_reason": ai_reason,
            "rule_explanation": rule_explanation,
            "academic_group": dwell_group_labels[idx] if idx < len(dwell_group_labels) else None,
            "must_try_tip": must_try_tip,
            "image_url": spot.get("image_url"),
            "open_hours": f"{spot.get('open_time')} - {spot.get('close_time')}",
            "price_range": f"{p_min_cost:,}đ - {p_max_cost:,}đ" if (p_min_cost > 0 or p_max_cost > 0) else "Miễn phí",
            "lat": p_lat,
            "lon": p_lon,
            "dist": dist,
            "t_min": t_min,
            "dwell_min": dwell_min
        }
        steps.append(step_dict)
        curr_lat, curr_lon = p_lat, p_lon

        stops_db_data.append({
            "place_id": spot.get("id"),
            "stop_order": idx + 1,
            "time_slot": slot_time,
            "action_title": action_title,
            "travel_distance_km": dist,
            "travel_time_minutes": t_min,
            "estimated_cost_min": p_min_cost,
            "estimated_cost_max": p_max_cost
        })

    # Tính tổng ngân sách & tổng thời gian (G6-FR05 MUST)
    total_min_cost = sum(spot.get("min_price", 0) for spot in optimized_places)
    total_max_cost = sum(spot.get("max_price", 0) for spot in optimized_places)
    total_dwell_mins = sum(proportional_dwells)
    total_duration_minutes = total_t_min + total_dwell_mins

    spare_time_minutes = max(0, free_duration - total_duration_minutes)
    spare_time_message = None
    if spare_time_minutes >= 20:
        dep_clock = clock_cursor
        end_h, end_m = (dep_clock // 60) % 24, dep_clock % 60
        spare_time_message = f"Lộ trình dự kiến hoàn thành lúc {end_h:02d}:{end_m:02d}. Bạn còn dư ~{spare_time_minutes} phút thong thả dạo phố, ngắm cảnh hoặc về sớm nghỉ ngơi!"

    is_within_budget = (target_budget == 0 and total_min_cost == 0) or (total_min_cost <= target_budget)
    is_within_time = total_duration_minutes <= (free_duration + 30)

    # Trạng thái AI minh bạch
    ai_status_message = (
        f"Được tối ưu bởi Google Gemini AI ({actual_model})" 
        if ai_status == "success" 
        else "Tối ưu tự động bởi Thuật toán Định tuyến SGGo (Chế độ dự phòng)"
    )

    # Lưu lịch trình vào CSDL SQLite (Section 5 ERD & Data Dictionary)
    itin_id = None
    target_user_id = req.user_id
    if target_user_id is None and isinstance(x_user_id, str) and x_user_id.isdigit():
        target_user_id = int(x_user_id)
    try:
        itin_id = save_itinerary({
            "user_id": target_user_id,
            "start_location": req.start_location,
            "start_lat": start_lat,
            "start_lon": start_lon,
            "free_time": req.free_time,
            "companion": req.companion,
            "purpose": req.purpose,
            "budget_level": req.budget_level or req.budget,
            "target_budget": target_budget,
            "total_estimated_budget_min": total_min_cost,
            "total_estimated_budget_max": total_max_cost,
            "total_duration_minutes": total_duration_minutes,
            "summary": overall_advice
        }, stops_db_data)
    except Exception as e:
        print(f"Lưu itinerary DB log: {e}")

    return {
        "feasible": True,
        "itinerary_id": itin_id,
        "summary": overall_advice,
        "steps": steps,
        "model_used": actual_model,
        "ai_status": ai_status,
        "ai_status_message": ai_status_message,
        "routing_source": routing_source,
        "routing_warning": routing_warning,
        "spare_time_minutes": spare_time_minutes,
        "spare_time_message": spare_time_message,
        "num_stops": len(optimized_places),
        "start_location": req.start_location,
        "start_coords": {"lat": start_lat, "lon": start_lon},
        "gmaps_multi_url": gmaps_multi_url,
        "kpi": {
            "target_budget": target_budget,
            "total_min_cost": total_min_cost,
            "total_max_cost": total_max_cost,
            "is_within_budget": is_within_budget,
            "free_duration_minutes": free_duration,
            "total_duration_minutes": total_duration_minutes,
            "spare_time_minutes": spare_time_minutes,
            "spare_time_message": spare_time_message,
            "total_travel_distance_km": round(total_dist, 2),
            "total_travel_time_minutes": total_t_min,
            "is_within_time": is_within_time
        }
    }



# ==============================================================================
# CÁC API QUẢN TRỊ DÀNH CHO ADMIN (ADMIN CRUD & IMPORT CSV)
# ==============================================================================

def validate_place_payload(place: PlaceModel):
    name = (place.name or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Tên địa điểm phải có ít nhất 2 ký tự!")
    
    cat = (place.category or "").strip().lower()
    if cat not in ["an_uong", "di_choi"]:
        raise HTTPException(status_code=400, detail="Thể loại địa điểm không hợp lệ (phải là 'an_uong' hoặc 'di_choi')!")
        
    addr = (place.address or "").strip()
    if len(addr) < 5:
        raise HTTPException(status_code=400, detail="Địa chỉ phải cụ thể (ít nhất 5 ký tự)!")

    # 1. Ràng buộc chuẩn hóa 22 Quận/Huyện của TP.HCM
    dist = (place.district or "").strip()
    if dist and dist not in VALID_DISTRICTS:
        raise HTTPException(status_code=400, detail=f"Khu vực '{dist}' không thuộc danh sách 22 quận/huyện hợp lệ của TP.HCM!")
        
    if place.lat is None or place.lon is None:
        raise HTTPException(status_code=400, detail="Tọa độ GPS (Vĩ độ và Kinh độ) là bắt buộc!")
        
    try:
        lat = float(place.lat)
        lon = float(place.lon)
    except Exception:
        raise HTTPException(status_code=400, detail="Tọa độ GPS phải là số thực hợp lệ!")
        
    if not (10.3 <= lat <= 11.2) or not (106.3 <= lon <= 107.2):
        raise HTTPException(status_code=400, detail="Tọa độ GPS nằm ngoài phạm vi TP.HCM (Vĩ độ: 10.3 - 11.2, Kinh độ: 106.3 - 107.2)!")
        
    # 2. Ràng buộc định dạng giờ mở/đóng cửa HH:MM
    time_regex = r'^([01]\d|2[0-3]):([0-5]\d)$'
    ot = (place.open_time or "").strip()
    if ot and not re.match(time_regex, ot):
        raise HTTPException(status_code=400, detail="Giờ mở cửa không đúng định dạng chuẩn (HH:MM, ví dụ: 08:00)!")
    ct = (place.close_time or "").strip()
    if ct and not re.match(time_regex, ct):
        raise HTTPException(status_code=400, detail="Giờ đóng cửa không đúng định dạng chuẩn (HH:MM, ví dụ: 22:00)!")

    # 3. Ràng buộc mức giá và biên trên 50 triệu VNĐ
    if place.min_price is not None and place.min_price < 0:
        raise HTTPException(status_code=400, detail="Mức giá tối thiểu không được là số âm!")
    if place.max_price is not None and place.max_price < 0:
        raise HTTPException(status_code=400, detail="Mức giá tối đa không được là số âm!")
    if (place.min_price is not None and place.min_price > 50000000) or (place.max_price is not None and place.max_price > 50000000):
        raise HTTPException(status_code=400, detail="Mức giá không được vượt quá 50,000,000 VNĐ!")
    if place.min_price is not None and place.max_price is not None:
        if place.max_price > 0 and place.max_price < place.min_price:
            raise HTTPException(status_code=400, detail="Mức giá tối đa không được nhỏ hơn mức giá tối thiểu!")
            
    if place.rating is not None and not (0.0 <= float(place.rating) <= 5.0):
        raise HTTPException(status_code=400, detail="Điểm đánh giá sao phải nằm trong khoảng từ 0.0 đến 5.0!")
        
    if place.reviews_count is not None and place.reviews_count < 0:
        raise HTTPException(status_code=400, detail="Số lượt đánh giá không được là số âm!")

    # 4. Ràng buộc toàn vẹn tham chiếu Thẻ ngữ cảnh (Tags)
    if place.tags:
        valid_tag_keys = set(t["tag_key"] for t in get_all_tags() if t.get("is_active", 1) == 1)
        if valid_tag_keys:
            raw_tags = []
            if "tier1:" in place.tags or "tier2:" in place.tags:
                for p in place.tags.split("|"):
                    p = p.strip()
                    if p.startswith("tier1:") or p.startswith("tier2:"):
                        raw_tags.extend([x.strip() for x in p.split(":", 1)[1].split(",") if x.strip()])
            else:
                raw_tags = [x.strip() for x in place.tags.split(",") if x.strip()]
            for t in raw_tags:
                if t not in valid_tag_keys:
                    raise HTTPException(status_code=400, detail=f"Thẻ ngữ cảnh '{t}' không tồn tại hoặc đã bị vô hiệu hóa trong hệ thống!")

@app.post("/api/admin/places", dependencies=[Depends(require_admin)])
def create_new_place(place: PlaceModel):
    validate_place_payload(place)

    # Kiểm tra chống trùng lặp đa lớp thông minh (Tên, Link Maps, Địa chỉ, GPS < 15m)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, address, lat, lon, google_maps_url FROM places")
    existing_places = [dict(r) for r in cursor.fetchall()]
    conn.close()

    from backend.database import find_duplicate_place
    dup_reason = find_duplicate_place(
        place.name, place.address, place.lat, place.lon, place.google_maps_url, place.category, existing_places
    )
    if dup_reason:
        raise HTTPException(status_code=400, detail=f"Địa điểm này đã tồn tại trong CSDL ({dup_reason})!")

    new_p = add_place(place.model_dump())
    return {"status": "ok", "place": new_p}

@app.put("/api/admin/places/{place_id}", dependencies=[Depends(require_admin)])
def modify_place(place_id: int, place: PlaceModel):
    validate_place_payload(place)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, address, lat, lon, google_maps_url FROM places")
    existing_places = [dict(r) for r in cursor.fetchall()]
    conn.close()

    from backend.database import find_duplicate_place
    dup_reason = find_duplicate_place(
        place.name, place.address, place.lat, place.lon, place.google_maps_url, place.category, existing_places, exclude_id=place_id
    )
    if dup_reason:
        raise HTTPException(status_code=400, detail=f"Không thể cập nhật: Dữ liệu bị trùng lặp với địa điểm khác trong CSDL ({dup_reason})!")

    updated = update_place(place_id, place.model_dump())
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa điểm để cập nhật.")
    return {"status": "ok", "place": updated}

@app.delete("/api/admin/places/{place_id}", dependencies=[Depends(require_admin)])
def remove_place(place_id: int):
    delete_place(place_id)
    return {"status": "ok", "message": "Đã xóa địa điểm thành công."}

@app.post("/api/admin/places/{place_id}/toggle-hide", dependencies=[Depends(require_admin)])
def toggle_admin_place_hide(place_id: int):
    res = toggle_hide_place(place_id)
    if not res:
        raise HTTPException(status_code=404, detail="Không tìm thấy địa điểm.")
    return {"status": "ok", "place": res}

@app.get("/api/admin/sample-csv", dependencies=[Depends(require_admin)])
def download_sample_csv():
    csv_text = generate_sample_csv()
    return Response(content=csv_text, media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=template_places.csv"
    })

@app.get("/api/admin/sample-excel", dependencies=[Depends(require_admin)])
def download_sample_excel():
    excel_bytes = generate_sample_excel()
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=template_places.xlsx"}
    )

def extract_real_place_chrome(target_url: str) -> dict:
    """Sử dụng Headless Chrome ngầm để render Google Maps và bóc tách chính xác 100% dữ liệu thật từ DOM (Địa chỉ số nhà, sao thật, giờ thật)"""
    import subprocess
    chrome_paths = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe')
    ]
    chrome_bin = next((p for p in chrome_paths if os.path.exists(p)), None)
    if not chrome_bin:
        return {}
    try:
        cmd = [chrome_bin, '--headless=new', '--dump-dom', '--virtual-time-budget=4000', target_url]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=8)
        html = res.stdout or ""
        details = {}

        # 1. Bóc tách số nhà và địa chỉ chính xác
        m_addr = re.search(r'data-item-id="address"[^>]*>.*?<div class="Io6YTe[^"]*"[^>]*>([^<]+)</div>', html, re.DOTALL)
        if not m_addr:
            m_addr = re.search(r'aria-label="(?:Địa chỉ|Address):\s*([^"]+)"', html)
        if m_addr:
            addr = m_addr.group(1).strip()
            addr = re.sub(r',\s*(?:Vietnam|Việt Nam)$', '', addr, flags=re.IGNORECASE).strip()
            addr = re.sub(r'\s*\b\d{5,6}\b,?', '', addr).strip(' ,')
            if "bàn cờ" in addr.lower() and "quận 3" not in addr.lower():
                addr = addr.replace("Bàn Cờ", "Phường Bàn Cờ, Quận 3")
            if not any(k in addr.lower() for k in ["tp", "hồ chí minh", "hcm", "saigon"]):
                addr += ", TP.HCM"
            elif "hồ chí minh" in addr.lower() and "tp" not in addr.lower():
                addr = re.sub(r'Hồ Chí Minh', 'TP.HCM', addr, flags=re.IGNORECASE)
            details["address"] = addr

        # 2. Bóc tách số sao thật (nếu có trên Maps)
        m_rating = re.search(r'aria-label="([0-9.,]+)\s*(?:stars?|sao)', html)
        if not m_rating:
            m_rating = re.search(r'<span class="ceNzKf"[^>]*aria-hidden="true">([0-9.,]+)</span>', html)
        if m_rating:
            try:
                val = float(m_rating.group(1).replace(",", "."))
                if 1.0 <= val <= 5.0:
                    details["rating"] = val
            except Exception:
                pass

        # 3. Bóc tách lượt review thật (nếu có trên Maps)
        m_rev = re.search(r'aria-label="([0-9.,]+)\s*(?:bài đánh giá|reviews?)', html)
        if not m_rev:
            m_rev = re.search(r'\((\d+[\d.,]*)\s*(?:bài đánh giá|reviews?|\))\s*<', html)
        if m_rev:
            try:
                clean_rev = re.sub(r'[.,]', '', m_rev.group(1))
                details["reviews_count"] = int(clean_rev)
            except Exception:
                pass

        # 4. Bóc tách giờ mở/đóng cửa thật (nếu có đăng ký trên Maps)
        time_str = ""
        for a in re.findall(r'aria-label="([^"]*?(?:to|–|-)\s*\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?[^"]*?)"', html):
            if any(w in a for w in ["AM", "PM", ":", "to", "–"]):
                time_str = a
                break

        if time_str:
            m_time = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?\s*(?:to|–|-)\s*(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?', time_str, re.IGNORECASE)
            if m_time:
                def to_24h(h, m, ampm):
                    h = int(h)
                    m = int(m or 0)
                    if ampm:
                        ampm = ampm.upper()
                        if ampm == "PM" and h < 12:
                            h += 12
                        elif ampm == "AM" and h == 12:
                            h = 0
                    return f"{h:02d}:{m:02d}"
                try:
                    details["open_time"] = to_24h(m_time.group(1), m_time.group(2), m_time.group(3))
                    details["close_time"] = to_24h(m_time.group(4), m_time.group(5), m_time.group(6))
                except Exception:
                    pass

        return details
    except Exception:
        pass
    return {}

@app.post("/api/admin/extract-gmaps", dependencies=[Depends(require_admin)])
def extract_gmaps_info(req: ExtractGmapsRequest):
    raw_input = req.url_or_query.strip()
    if not raw_input:
        raise HTTPException(status_code=400, detail="Vui lòng dán liên kết Google Maps vào ô nhập liệu.")

    extracted_name = ""
    extracted_address = ""
    extracted_district = "TP.HCM"
    extracted_lat = None
    extracted_lon = None
    extracted_image = ""
    extracted_rating = None
    extracted_reviews_count = None
    extracted_open_time = ""
    extracted_close_time = ""

    target_url = raw_input
    text_before = ""
    m_url = re.search(r'https?://[^\s]+', raw_input)
    if m_url:
        target_url = m_url.group(0).rstrip(")>]\"'")
        text_before = raw_input.replace(m_url.group(0), "").strip(" ·,-\n\t")
    elif target_url.startswith("google.com") or target_url.startswith("www.google.com") or target_url.startswith("maps.google.com"):
        target_url = "https://" + target_url

    is_url = (target_url.startswith("http://") or 
              target_url.startswith("https://") or 
              "maps." in target_url or 
              "goo.gl" in target_url or 
              "google.com" in target_url)

    if not is_url:
        raise HTTPException(
            status_code=400, 
            detail="Hệ thống chỉ hỗ trợ bóc tách từ đường link Google Maps hợp lệ (đã ngừng chức năng nhập tên quán để tránh dữ liệu sai lệch). Quý Admin vui lòng dán đúng đường link Google Maps hoặc tự nhập thông tin vào form bên dưới."
        )

    # Nếu người dùng copy nguyên đoạn chia sẻ có sẵn tên và địa chỉ
    if text_before:
        parts = [p.strip() for p in re.split(r'[·–—|]|\s*-\s*', text_before) if p.strip()]
        if len(parts) >= 2:
            extracted_name = parts[0]
            extracted_address = ", ".join(parts[1:])
        elif len(parts) == 1:
            if any(k in parts[0] for k in ["Đường", "Phường", "Quận", "TP.", "Hồ Chí Minh"]):
                extracted_address = parts[0]
            else:
                extracted_name = parts[0]

    import requests

    # 1. BÓC TÁCH NGAY TỪ LINK GỐC (0ms, KHÔNG CẦN CHỜ MẠNG)
    m_direct_place = re.search(r'/place/([^/@?]+)', target_url)
    if m_direct_place:
        extracted_name = urllib.parse.unquote_plus(m_direct_place.group(1)).replace("+", " ").strip()

    m_direct_coords = re.search(r'/@([0-9.]+),([0-9.]+)', target_url)
    if not m_direct_coords:
        m_direct_coords = re.search(r'!3d([0-9.]+)!4d([0-9.]+)', target_url)
    if not m_direct_coords:
        m_direct_coords = re.search(r'[?&](?:q|ll)=([0-9.]+),([0-9.]+)', target_url)
    if m_direct_coords:
        try:
            extracted_lat = float(m_direct_coords.group(1))
            extracted_lon = float(m_direct_coords.group(2))
        except Exception:
            pass

    # 2. CHỈ GỌI MẠNG NẾU LÀ LINK RÚT GỌN HOẶC CHƯA CÓ ĐỦ TÊN VÀ TỌA ĐỘ
    need_network = (not extracted_name or extracted_lat is None or extracted_lon is None)
    if need_network:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept-Language": "vi,en;q=0.9"
            }
            resp = requests.get(target_url, allow_redirects=True, timeout=3.5, headers=headers)
            final_url = resp.url
            html = resp.text

            # Kiểm tra redirect qua thẻ meta refresh nếu có (maps.app.goo.gl)
            if "maps.app.goo.gl" in final_url or "goo.gl/maps" in final_url:
                meta_ref = re.search(r"""<meta[^>]+http-equiv=["']refresh["'][^>]+content=["'][0-9]+;\s*url=([^"']+)["']""", html, re.IGNORECASE)
                if meta_ref:
                    final_url = meta_ref.group(1).replace("&amp;", "&")

            if not extracted_name:
                m_place = re.search(r'/place/([^/@?]+)', final_url)
                if m_place:
                    extracted_name = urllib.parse.unquote_plus(m_place.group(1)).replace("+", " ").strip()
                elif "/search/" in final_url:
                    m_search = re.search(r'/search/([^/@?]+)', final_url)
                    if m_search:
                        extracted_name = urllib.parse.unquote_plus(m_search.group(1)).replace("+", " ").strip()
                elif "?q=" in final_url or "&q=" in final_url or "?query=" in final_url:
                    m_q = re.search(r'[?&](?:q|query)=([^&]+)', final_url)
                    if m_q:
                        extracted_name = urllib.parse.unquote_plus(m_q.group(1)).replace("+", " ").strip()

            if extracted_lat is None or extracted_lon is None:
                m_coords = re.search(r'/@([0-9.]+),([0-9.]+)', final_url)
                if m_coords:
                    extracted_lat = float(m_coords.group(1))
                    extracted_lon = float(m_coords.group(2))
                else:
                    m_data_coords = re.search(r'!3d([0-9.]+)!4d([0-9.]+)', final_url)
                    if m_data_coords:
                        extracted_lat = float(m_data_coords.group(1))
                        extracted_lon = float(m_data_coords.group(2))
                    else:
                        m_q_coords = re.search(r'[?&](?:q|ll)=([0-9.]+),([0-9.]+)', final_url)
                        if m_q_coords:
                            extracted_lat = float(m_q_coords.group(1))
                            extracted_lon = float(m_q_coords.group(2))

            og_img = re.search(r"""<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""", html)
            if og_img and ("googleusercontent" in og_img.group(1) or "streetview" in og_img.group(1)):
                extracted_image = og_img.group(1)
        except Exception:
            pass

    # Nếu tên quán có chứa luôn địa chỉ dạng "Tên Quán, Số nhà, Phường, Quận..."
    if "," in extracted_name and any(k in extracted_name for k in ["Quận", "Phường", "Đường"]):
        parts = extracted_name.split(",", 1)
        extracted_name = parts[0].strip()
        extracted_address = parts[1].strip()

    if not extracted_name or extracted_name.startswith("http"):
        extracted_name = raw_input.rstrip("/").split("/")[-1].replace("+", " ").replace("-", " ")

    if re.match(r'^[0-9.,\s]+$', extracted_name):
        extracted_name = ""
    else:
        extracted_name = ' '.join(w.capitalize() for w in extracted_name.split())

    # 2.5. TRÍCH XUẤT ĐỊA CHỈ CHUẨN XÁC 100% SỐ NHÀ, SAO VÀ GIỜ THẬT BẰNG HEADLESS CHROME DOM
    if target_url and target_url.startswith("http"):
        chrome_details = extract_real_place_chrome(target_url)
        if not extracted_address and chrome_details.get("address"):
            extracted_address = chrome_details["address"]
        if chrome_details.get("rating") is not None:
            extracted_rating = chrome_details["rating"]
        if chrome_details.get("reviews_count") is not None:
            extracted_reviews_count = chrome_details["reviews_count"]
        if chrome_details.get("open_time"):
            extracted_open_time = chrome_details["open_time"]
        if chrome_details.get("close_time"):
            extracted_close_time = chrome_details["close_time"]

    # 3. REVERSE GEOCODING TỪ TỌA ĐỘ GPS (CÓ FALLBACK CSDL CỰC KỲ AN TOÀN)
    if extracted_lat is not None and extracted_lon is not None:
        # 3a. Thử tra OpenStreetMap với timeout ngắn 2.0s (chỉ chạy nếu chưa có địa chỉ chính xác)
        if not extracted_address:
            try:
                osm_res = requests.get(
                    f"https://nominatim.openstreetmap.org/reverse?format=json&lat={extracted_lat}&lon={extracted_lon}&addressdetails=1",
                    headers={"User-Agent": "SGGo-Travel-Guide/1.0"},
                    timeout=2.0
                )
                if osm_res.ok:
                    osm_data = osm_res.json()
                    addr_data = osm_data.get("address", {})
                    road = addr_data.get("road", "")
                    suburb = addr_data.get("suburb", "")
                    district_osm = addr_data.get("city_district") or addr_data.get("district") or ""
                    parts = []
                    for p in [road, suburb, district_osm, "TP.HCM"]:
                        p_clean = p.strip()
                        if p_clean and p_clean not in parts:
                            parts.append(p_clean)
                    if parts:
                        extracted_address = ", ".join(parts)
                    # Bóc tách quận từ dữ liệu OSM
                    all_districts = ["Quận 1", "Quận 3", "Quận 4", "Quận 5", "Quận 6", "Quận 7", "Quận 8", "Quận 10", "Quận 11", "Quận 12", "Bình Thạnh", "Gò Vấp", "Phú Nhuận", "Tân Bình", "Tân Phú", "Bình Tân", "Thủ Đức", "TP. Thủ Đức", "Bình Chánh", "Hóc Môn", "Củ Chi", "Nhà Bè", "Cần Giờ"]
                    for d in all_districts:
                        if d.lower() in extracted_address.lower() or d.lower() in str(addr_data).lower() or ('bàn cờ' in extracted_address.lower() and d == 'Quận 3'):
                            extracted_district = d
                            break
            except Exception:
                pass

        # 3b. FALLBACK CSDL NỘI BỘ (0ms, KHÔNG CẦN INTERNET, CHUẨN XÁC VỚI 201 ĐỊA ĐIỂM SÀI GÒN)
        if extracted_district == "TP.HCM" or not extracted_address:
            try:
                conn_fb = get_connection()
                cursor_fb = conn_fb.cursor()
                cursor_fb.execute("SELECT name, district, address, lat, lon FROM places WHERE lat IS NOT NULL AND lon IS NOT NULL")
                rows = cursor_fb.fetchall()
                conn_fb.close()
                if rows:
                    import math
