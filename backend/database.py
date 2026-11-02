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

        # Lớp 1: Trùng tên 100%
        if clean_name and p_name and clean_name == p_name:
            return f"Trùng tên 100% với quán '{p.get('name')}' (ID #{p.get('id', '?')})"

        # Lớp 2: Trùng link Google Maps thực tế
        if clean_maps and p_maps and clean_maps == p_maps and "search/?api=1" not in clean_maps:
            return f"Trùng liên kết Google Maps với quán '{p.get('name')}' (ID #{p.get('id', '?')})"

        # Lớp 3: Trùng địa chỉ (KỂ CẢ TÊN KHÁC NHAU HOẶC CHƯA NHẬP TÊN!)
        if clean_addr and p_addr:
            # 3A. Khớp 100% chuỗi địa chỉ
            if clean_addr == p_addr:
                return f"Trùng hoàn toàn địa chỉ ('{p.get('address')}') với quán '{p.get('name')}' (ID #{p.get('id', '?')})"

            # 3B. Khớp số nhà / tên đường qua addresses_match
            if addresses_match(new_addr, p.get("address")):
                if not new_is_complex and not p_is_complex:
                    return f"Trùng hoàn toàn địa chỉ ('{p.get('address')}') với quán '{p.get('name')}' (ID #{p.get('id', '?')})"
                else:
                    # Nếu trong TTTM/Phức hợp mà trùng cả số tầng
                    if new_floor and p_floor and new_floor == p_floor:
                        return f"Trùng địa chỉ và cùng số tầng ({new_floor}) với quán '{p.get('name')}' (ID #{p.get('id', '?')})"
                    if has_brand_overlap(new_name, p.get("name")):
                        return f"Trùng địa chỉ và tên thương hiệu tương đồng với quán '{p.get('name')}' (ID #{p.get('id', '?')})"

        # Phân biệt rạch ròi giữa TTTM (di_choi) và nhà hàng (an_uong) bên trong TTTM
        if (new_is_complex or p_is_complex) and new_cat and p_cat and ((new_cat == 'di_choi' and p_cat == 'an_uong') or (new_cat == 'an_uong' and p_cat == 'di_choi')):
            continue

        # Lớp 4: Tọa độ GPS trùng sát (< 15 mét)
        if lat and lon and p_lat and p_lon:
            dist = haversine_distance_meters(lat, lon, p_lat, p_lon)
            if dist < 15.0:
                if has_brand_overlap(new_name, p.get("name")):
                    return f"Tọa độ GPS trùng sát (~{round(dist)}m) và cùng thương hiệu với quán '{p.get('name')}' (ID #{p.get('id', '?')})"
                if addresses_match(new_addr, p.get("address")):
                    return f"Tọa độ GPS trùng sát (~{round(dist)}m) và cùng địa chỉ với quán '{p.get('name')}' (ID #{p.get('id', '?')})"
                if dist < 5.0 and not new_is_complex and not p_is_complex:
                    num1, st1 = split_house_number_and_street(new_addr)
                    num2, st2 = split_house_number_and_street(p.get("address"))
                    if not (num1 and num2 and num1 != num2):
                        return f"Tọa độ GPS trùng sát (~{round(dist)}m) với quán '{p.get('name')}' (ID #{p.get('id', '?')}) tại '{p.get('address')}'"

        # Lớp 5: Tên chứa nhau và trùng địa chỉ / đường
        if has_brand_overlap(new_name, p.get("name")) and clean_addr and p_addr:
            if clean_addr in p_addr or p_addr in clean_addr or clean_addr[:15] == p_addr[:15]:
                return f"Tên và địa chỉ rất tương đồng với quán '{p.get('name')}' (ID #{p.get('id', '?')})"

    return None

def migrate_schema_constraints(conn):
    """Tự động kiểm tra và nâng cấp ràng buộc CHECK DDL cho SQLite mà không làm mất dữ liệu"""
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='places'")
    row = cursor.fetchone()
    if row and "CHECK" not in row[0]:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        CREATE TABLE places_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL CHECK (category IN ('an_uong', 'di_choi')),
            address TEXT NOT NULL,
            district TEXT NOT NULL DEFAULT 'Quận 5',
            lat REAL NOT NULL CHECK ((lat BETWEEN 10.3 AND 11.2) OR lat = 0.0),
            lon REAL NOT NULL CHECK ((lon BETWEEN 106.3 AND 107.2) OR lon = 0.0),
            open_time TEXT NOT NULL DEFAULT '08:00',
            close_time TEXT NOT NULL DEFAULT '22:00',
            min_price INTEGER NOT NULL DEFAULT 30000 CHECK (min_price >= 0),
            max_price INTEGER NOT NULL DEFAULT 100000 CHECK (max_price >= 0 AND (max_price = 0 OR max_price >= min_price)),
            rating REAL NOT NULL DEFAULT 4.5 CHECK (rating >= 0.0 AND rating <= 5.0),
            reviews_count INTEGER NOT NULL DEFAULT 100 CHECK (reviews_count >= 0),
            peak_hours TEXT DEFAULT '18:00 - 20:00',
            best_review TEXT DEFAULT 'Quán sạch sẽ, đồ ăn ngon, phục vụ nhanh.',
            worst_review TEXT DEFAULT 'Giờ cao điểm hơi đông khách, nên đi sớm.',
            image_url TEXT,
            tags TEXT DEFAULT 'nhom_ban',
            is_verified INTEGER NOT NULL DEFAULT 1 CHECK (is_verified IN (0, 1)),
            is_verified_review INTEGER NOT NULL DEFAULT 1 CHECK (is_verified_review IN (0, 1)),
            is_admin_choice INTEGER NOT NULL DEFAULT 0 CHECK (is_admin_choice IN (0, 1)),
            price_display TEXT,
            hours_display TEXT,
            is_hidden INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0, 1)),
            google_maps_url TEXT
        );
        """)
        cursor.execute("PRAGMA table_info(places)")
        cols = [r["name"] for r in cursor.fetchall()]
        col_str = ", ".join(cols)
        cursor.execute(f"INSERT INTO places_v2 ({col_str}) SELECT {col_str} FROM places")
        cursor.execute("DROP TABLE places")
        cursor.execute("ALTER TABLE places_v2 RENAME TO places")
        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    row = cursor.fetchone()
    if row and "CHECK" not in row[0]:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        CREATE TABLE users_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("PRAGMA table_info(users)")
        cols = [r["name"] for r in cursor.fetchall()]
        col_str = ", ".join(cols)
        cursor.execute(f"INSERT INTO users_v2 ({col_str}) SELECT {col_str} FROM users")
        cursor.execute("DROP TABLE users")
        cursor.execute("ALTER TABLE users_v2 RENAME TO users")
        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")

    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='tags'")
    row = cursor.fetchone()
    if row and "CHECK" not in row[0]:
        cursor.execute("PRAGMA foreign_keys = OFF;")
        cursor.execute("BEGIN TRANSACTION;")
        cursor.execute("""
        CREATE TABLE tags_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tag_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            tier_type TEXT DEFAULT 'companion' CHECK (length(tier_type) >= 1),
            is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        cursor.execute("PRAGMA table_info(tags)")
        cols = [r["name"] for r in cursor.fetchall()]
        col_str = ", ".join(cols)
        cursor.execute(f"INSERT INTO tags_v2 ({col_str}) SELECT {col_str} FROM tags")
        cursor.execute("DROP TABLE tags")
        cursor.execute("ALTER TABLE tags_v2 RENAME TO tags")
        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON;")

def migrate_existing_user_passwords(conn):
    """Tự động mã hóa băm SHA-256 các mật khẩu tài khoản cũ dạng plaintext"""
    cursor = conn.cursor()
    cursor.execute("SELECT id, password FROM users")
    users = cursor.fetchall()
    for u in users:
        pwd = u["password"]
        if pwd and not str(pwd).startswith("sha256:"):
            new_hash = hash_password(pwd)
            cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_hash, u["id"]))
    conn.commit()

def init_db():
    """Khởi tạo cấu trúc các bảng và nạp dữ liệu mẫu ban đầu"""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. BẢNG USERS (Tài khoản & Phân quyền)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. BẢNG PLACES (Thông tin địa điểm thực tế tại TP.HCM)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS places (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL CHECK (category IN ('an_uong', 'di_choi')),
        address TEXT NOT NULL,
        district TEXT NOT NULL DEFAULT 'Quận 5',
        lat REAL NOT NULL CHECK ((lat BETWEEN 10.3 AND 11.2) OR lat = 0.0),
        lon REAL NOT NULL CHECK ((lon BETWEEN 106.3 AND 107.2) OR lon = 0.0),
        open_time TEXT NOT NULL DEFAULT '08:00',
        close_time TEXT NOT NULL DEFAULT '22:00',
        min_price INTEGER NOT NULL DEFAULT 30000 CHECK (min_price >= 0),
        max_price INTEGER NOT NULL DEFAULT 100000 CHECK (max_price >= 0 AND (max_price = 0 OR max_price >= min_price)),
        rating REAL NOT NULL DEFAULT 4.5 CHECK (rating >= 0.0 AND rating <= 5.0),
        reviews_count INTEGER NOT NULL DEFAULT 100 CHECK (reviews_count >= 0),
        peak_hours TEXT DEFAULT '18:00 - 20:00',
        best_review TEXT DEFAULT 'Quán sạch sẽ, đồ ăn ngon, phục vụ nhanh.',
        worst_review TEXT DEFAULT 'Giờ cao điểm hơi đông khách, nên đi sớm.',
        image_url TEXT,
        tags TEXT DEFAULT 'nhom_ban',
        is_verified INTEGER NOT NULL DEFAULT 1 CHECK (is_verified IN (0, 1)),
        is_verified_review INTEGER NOT NULL DEFAULT 1 CHECK (is_verified_review IN (0, 1)),
        is_admin_choice INTEGER NOT NULL DEFAULT 0 CHECK (is_admin_choice IN (0, 1)),
        price_display TEXT,
        hours_display TEXT,
