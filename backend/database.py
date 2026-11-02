# -*- coding: utf-8 -*-
"""
database.py - QUẢN LÝ CƠ SỞ DỮ LIỆU SQLITE CHO DỰ ÁN SGGO!
Môn học: Công nghệ Phần mềm (COMP1044)

Kiến trúc chuẩn CNPM:
- Bảng users: Quản lý đăng ký, đăng nhập và phân quyền (Admin / User thường).
- Bảng places: Quản lý thông tin 201 địa điểm thực tế tại TP.HCM.
- Bảng tags & place_tags: Quản lý phân loại nhãn địa điểm.
- Bảng itineraries & itinerary_stops: Quản lý lịch trình và các điểm dừng.
- Bảng import_logs: Quản lý nhật ký nạp dữ liệu Excel/CSV.
- Hỗ trợ đầy đủ các thao tác CRUD và Import/Export file CSV có kiểm tra dữ liệu.
"""

import os
import sqlite3
import csv
import io
import json
import re
import unicodedata
import hashlib
import secrets

DB_PATH = os.path.join(os.path.dirname(__file__), "sggo.db")
ENRICHED_JSON_PATH = os.path.join(os.path.dirname(__file__), "enriched_places.json")

def get_connection():
    """Tạo kết nối tới file SQLite, kích hoạt khóa ngoại PRAGMA foreign_keys = ON, trả về sqlite3.Row"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    """Băm mật khẩu an toàn chuẩn mật mã SHA-256 kèm salt ngẫu nhiên 16 bytes"""
    if not password:
        return ""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"sha256:{salt}:{hashed}"

def verify_password(stored_password: str, input_password: str) -> bool:
    """
    Xác minh mật khẩu:
    - Nếu đã băm dạng sha256:salt:hash -> kiểm tra hash bằng hằng số thời gian compare_digest
    - Nếu là mật khẩu cũ chưa băm (legacy plaintext) -> so sánh trực tiếp
    """
    if not stored_password or not input_password:
        return False
    if str(stored_password).startswith("sha256:"):
        parts = str(stored_password).split(":")
        if len(parts) == 3:
            salt = parts[1]
            expected_hash = parts[2]
            computed_hash = hashlib.sha256((salt + input_password).encode("utf-8")).hexdigest()
            return secrets.compare_digest(computed_hash, expected_hash)
        return False
    return stored_password == input_password

def sanitize_cell_value(val):
    """Bảo vệ chống lỗ hổng CSV/Excel Formula Injection (CWE-1236)"""
    if val is None:
        return ""
    s = str(val)
    if len(s) > 0 and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s
    return s

def expand_address_abbreviations(text: str) -> str:
    """Mở rộng các từ viết tắt phổ biến trong địa chỉ Việt Nam (đ., p., q., tp., tttm, ...)"""
    if not text:
        return ""
    s = " " + str(text) + " "
    s = re.sub(r'(?<=\s|\W)(?:đ|d)\.\s*', 'đường ', s, flags=re.IGNORECASE)
    s = re.sub(r'(?<=\s|\W)(?:đ|d)\s+(?=[a-zà-ỹ0-9])', 'đường ', s, flags=re.IGNORECASE)
    s = re.sub(r'(?<=\s|\W)p\.\s*', 'phường ', s, flags=re.IGNORECASE)
    s = re.sub(r'(?<=\s|\W)p\s*(?=[0-9]+)', 'phường ', s, flags=re.IGNORECASE)
    s = re.sub(r'(?<=\s|\W)q\.\s*', 'quận ', s, flags=re.IGNORECASE)
    s = re.sub(r'(?<=\s|\W)q\s*(?=[0-9]+)', 'quận ', s, flags=re.IGNORECASE)
    s = re.sub(r'(?<=\s|\W)tp\.\s*', 'thành phố ', s, flags=re.IGNORECASE)
    s = re.sub(r'(?:tp\.?\s*hcm|tp\.?\s*hồ\s*chí\s*minh|tphcm|hồ\s*chí\s*minh)', 'thành phố hồ chí minh', s, flags=re.IGNORECASE)
    s = re.sub(r'\btttm\b', 'trung tâm thương mại', s, flags=re.IGNORECASE)
    s = re.sub(r'\bkdc\b', 'khu dân cư', s, flags=re.IGNORECASE)
    s = re.sub(r'\bt(\d+)\b', r'tầng \1', s, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', s).strip()

def normalize_search_text(s: str) -> str:
    """Chuẩn hóa chuỗi văn bản bỏ dấu tiếng Việt, chữ thường, bỏ ký tự đặc biệt, mở rộng viết tắt"""
    if not s:
        return ""
    import unicodedata, re
    s = expand_address_abbreviations(str(s))
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace('đ', 'd').replace('Đ', 'D').lower()
    return re.sub(r'[^a-z0-9]', '', s)

def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Tính khoảng cách mét giữa 2 tọa độ GPS"""
