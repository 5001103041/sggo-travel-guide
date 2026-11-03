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
