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
    import math
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

COMMERCIAL_COMPLEX_KEYWORDS = [
    "mall", "plaza", "center", "centre", "tttm", "bitexco", "landmark",
    "tầng ", "tang ", "lầu ", "lau ", "food court", "parkson", "takashimaya",
    "vincom", "aeon", "crescent", "gigamall", "nowzone", "sc vivocity",
    "lotte mart", "vạn hạnh mall", "van hanh mall", "chợ ", "cho ",
    "bạch đằng", "bach dang", "công viên", "cong vien", "thảo cầm viên", "thao cam vien", "bảo tàng", "bao tang"
]

GENERIC_BRAND_WORDS = {
    "quan", "nha", "hang", "tiem", "ca", "phe", "cafe", "tra", "sua", "buffet", "vietnam", "am", "thuc", "food", "coffee", "tea",
    "van", "hanh", "mall", "plaza", "center", "centre", "tttm", "vincom", "aeon", "hung", "vuong", "bitexco", "landmark", "crescent",
    "gigamall", "nowzone", "takashimaya", "parkson", "lotte", "bach", "dang", "cho", "ben", "thanh"
}

def is_commercial_complex(addr, name=""):
    """Xác định xem địa chỉ hoặc tên có phải là TTTM / Phức hợp lớn hay không."""
    text = (str(addr or "") + " " + str(name or "")).lower()
    return any(k in text for k in COMMERCIAL_COMPLEX_KEYWORDS)

def normalize_address_for_split(text):
    """Chuẩn hóa địa chỉ nhưng giữ lại dấu phẩy để phân tách số nhà + đường"""
    if not text:
        return ""
    text = expand_address_abbreviations(str(text))
    text = unicodedata.normalize('NFD', text)
    text = re.sub(r'[\u0300-\u036f]', '', text)
    text = text.replace('đ', 'd').replace('Đ', 'd')
    text = re.sub(r'[^a-zA-Z0-9\s,]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()

def split_house_number_and_street(text):
    """Tách số nhà và tên đường từ chuỗi địa chỉ"""
    if not text:
        return "", ""
    norm = normalize_address_for_split(text)
    part = norm.split(",")[0].strip()
    m = re.match(r'^([0-9]+[a-z0-9\/\-]*)(\s+)(.*)$', part)
    if m:
        num = m.group(1).strip()
        street = m.group(3).strip()
        return num, street
    return "", part

def extract_floor_number(text):
    """Trích xuất số tầng (tầng 4, lầu 3, floor 2...) từ chuỗi địa chỉ nếu có"""
    if not text:
        return ""
    t = unicodedata.normalize('NFD', str(text))
    t = re.sub(r'[\u0300-\u036f]', '', t).replace('đ', 'd').replace('Đ', 'd').lower()
    m = re.search(r'(tang\s*[0-9]+|lau\s*[0-9]+|floor\s*[0-9]+|tang\s*tret|lau\s*tret|tang\s*lung|l[0-9]{1,2})', t)
    if m:
        return re.sub(r'\s+', '', m.group(1))
    return ""

def addresses_match(addr1, addr2):
    """Kiểm tra hai chuỗi địa chỉ có cùng một số nhà và tên đường hay không"""
    c1 = normalize_search_text(addr1)
    c2 = normalize_search_text(addr2)
    if not c1 or not c2:
        return False
    if c1 == c2:
        return True
    
    num1, street1 = split_house_number_and_street(addr1)
    num2, street2 = split_house_number_and_street(addr2)
    
    if num1 and num2 and street1 and street2:
        if num1 == num2:
            st1 = re.sub(r'^(duong|d)\s+', '', street1).strip()
            st2 = re.sub(r'^(duong|d)\s+', '', street2).strip()
            if st1 == st2 or (len(st1) >= 6 and len(st2) >= 6 and (st1 in st2 or st2 in st1)):
                return True
        return False

    if len(c1) >= 12 and len(c2) >= 12:
        if c1 in c2 or c2 in c1:
            return True
        if len(c1) >= 16 and len(c2) >= 16 and c1[:16] == c2[:16]:
            return True
    return False

def has_brand_overlap(name1, name2):
    """Kiểm tra sự trùng lặp hoặc tương đồng về thương hiệu giữa hai tên quán"""
    c1 = normalize_search_text(name1)
    c2 = normalize_search_text(name2)
    if not c1 or not c2:
        return False
    if c1 == c2:
        return True
    if len(c1) >= 4 and len(c2) >= 4 and (c1 in c2 or c2 in c1):
        return True
    
    tokens1 = [w for w in c1.split() if len(w) >= 3 and w not in GENERIC_BRAND_WORDS]
    tokens2 = [w for w in c2.split() if len(w) >= 3 and w not in GENERIC_BRAND_WORDS]
    common = set(tokens1) & set(tokens2)
    return len(common) > 0

def find_duplicate_place(new_name, new_addr, new_lat, new_lon, new_maps, new_cat, existing_places, exclude_id=None):
    """
    Kiểm tra chống trùng lặp địa điểm thông minh đa lớp:
    1. Trùng 100% tên chuẩn hóa (không phân biệt dấu, hoa thường, khoảng trắng)
    2. Trùng link Google Maps thực tế
    3. Trùng 100% địa chỉ chuỗi chuẩn hóa (kể cả tên quán hoàn toàn khác!)
    4. Trùng địa chỉ nhà mặt phố hoặc cùng số tầng trong TTTM
    5. Tọa độ GPS trùng sát (< 15 mét) và địa chỉ hoặc tên tương đồng
    6. Tên tương đồng và cùng nằm trên cùng địa chỉ / đường
    """
    clean_name = normalize_search_text(new_name)
    clean_addr = normalize_search_text(new_addr)
    clean_maps = (new_maps or "").strip().lower()
    try:
        lat = float(new_lat or 0)
    except Exception:
        lat = 0.0
    try:
        lon = float(new_lon or 0)
    except Exception:
        lon = 0.0

    new_is_complex = is_commercial_complex(new_addr, new_name)
    new_floor = extract_floor_number(new_addr)

    for p in existing_places:
        if exclude_id is not None and str(p.get("id")) == str(exclude_id):
            continue

        p_name = normalize_search_text(p.get("name"))
        p_addr = normalize_search_text(p.get("address"))
        p_cat = p.get("category", "")
        p_maps = (p.get("google_maps_url") or "").strip().lower()
        try:
            p_lat = float(p.get("lat") or 0)
        except Exception:
            p_lat = 0.0
        try:
            p_lon = float(p.get("lon") or 0)
        except Exception:
            p_lon = 0.0

        p_is_complex = is_commercial_complex(p.get("address"), p.get("name"))
        p_floor = extract_floor_number(p.get("address"))
