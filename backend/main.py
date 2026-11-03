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

