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
        is_hidden INTEGER NOT NULL DEFAULT 0 CHECK (is_hidden IN (0, 1)),
        google_maps_url TEXT
    );
    """)

    # Tự động migrate cột is_admin_choice và is_hidden nếu dùng CSDL cũ
    cursor.execute("PRAGMA table_info(places)")
    existing_cols = [r["name"] for r in cursor.fetchall()]
    if "is_admin_choice" not in existing_cols:
        cursor.execute("ALTER TABLE places ADD COLUMN is_admin_choice INTEGER DEFAULT 0")
        conn.commit()
    if "is_hidden" not in existing_cols:
        cursor.execute("ALTER TABLE places ADD COLUMN is_hidden INTEGER DEFAULT 0")
        conn.commit()
    if "google_maps_url" not in existing_cols:
        cursor.execute("ALTER TABLE places ADD COLUMN google_maps_url TEXT")
        conn.commit()



    # 4. BẢNG ITINERARIES (Lưu trữ lịch trình theo yêu cầu Section 5 đề tài)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS itineraries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        start_location TEXT NOT NULL,
        start_lat REAL,
        start_lon REAL,
        free_time TEXT NOT NULL,
        companion TEXT DEFAULT 'ban_be',
        purpose TEXT DEFAULT 'ca_hai',
        budget_level TEXT DEFAULT '100k_250k',
        target_budget INTEGER DEFAULT 250000,
        total_estimated_budget_min INTEGER DEFAULT 0,
        total_estimated_budget_max INTEGER DEFAULT 0,
        total_duration_minutes INTEGER DEFAULT 0,
        summary TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """)

    # 5. BẢNG ITINERARY_STOPS (Các chặng dừng trong lịch trình theo yêu cầu Section 5 đề tài)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS itinerary_stops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        itinerary_id INTEGER NOT NULL,
        place_id INTEGER NOT NULL,
        stop_order INTEGER NOT NULL,
        time_slot TEXT,
        action_title TEXT,
        travel_distance_km REAL,
        travel_time_minutes INTEGER,
        estimated_cost_min INTEGER DEFAULT 0,
        estimated_cost_max INTEGER DEFAULT 0,
        FOREIGN KEY (itinerary_id) REFERENCES itineraries(id) ON DELETE CASCADE,
        FOREIGN KEY (place_id) REFERENCES places(id) ON DELETE CASCADE
    );
    """)

    # 6. BẢNG IMPORT_LOGS (Lịch sử nạp CSV & Báo cáo dòng lỗi theo yêu cầu G6-FR09 & Section 5)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS import_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL DEFAULT 'uploaded_places.csv',
        total_rows INTEGER NOT NULL DEFAULT 0,
        success_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        error_details_json TEXT,
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 7. BẢNG TAGS (Danh mục thẻ ngữ cảnh theo yêu cầu G6-FR08 & Section 5 ERD)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_key TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        tier_type TEXT DEFAULT 'companion' CHECK (length(tier_type) >= 1),
        is_active INTEGER DEFAULT 1 CHECK (is_active IN (0, 1)),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 8. BẢNG PLACE_TAGS (Bảng quan hệ nhiều-nhiều giữa Place và Tag theo Section 5 ERD)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS place_tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        place_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        tier INTEGER DEFAULT 1,
        FOREIGN KEY (place_id) REFERENCES places(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE,
        UNIQUE(place_id, tag_id)
    );
    """)

    conn.commit()

    # Nâng cấp các bảng cũ lên chuẩn CHECK constraints nếu cần
    migrate_schema_constraints(conn)
    migrate_existing_user_passwords(conn)

    # Khởi tạo dữ liệu mẫu nếu bảng còn trống
    seed_users_if_needed(conn)
    seed_places_if_needed(conn)
    seed_tags_if_needed(conn)
    conn.close()

def seed_users_if_needed(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users (username, password, full_name, role) VALUES 
        ('admin', ?, 'Quản Trị Viên SGGo', 'admin'),
        ('user1', ?, 'Nguyễn Văn A', 'user');
        """, (hash_password('admin123'), hash_password('123456')))
        conn.commit()
    seed_places_if_needed(conn)
    seed_tags_if_needed(conn)
    conn.close()

def seed_users_if_needed(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
        INSERT INTO users (username, password, full_name, role) VALUES 
        ('admin', 'admin123', 'Quản Trị Viên SGGo', 'admin'),
        ('user1', '123456', 'Nguyễn Văn A', 'user');
        """)
        conn.commit()

def seed_places_if_needed(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM places")
    if cursor.fetchone()[0] > 0:
        return

    # Đọc 40 quán thực tế từ enriched_places.json
    places_to_insert = []
    if os.path.exists(ENRICHED_JSON_PATH):
        with open(ENRICHED_JSON_PATH, "r", encoding="utf-8") as f:
            raw_places = json.load(f)
            
            for p in raw_places:
                name = p.get("name")
                if not name:
                    continue
                category = p.get("category", "an_uong")
                addr = p.get("address") or p.get("full_address") or "Quận 5, TP.HCM"
                district = p.get("district", "Quận 5")
                lat = float(p.get("lat") or 0.0)
                lon = float(p.get("lon") or 0.0)
                open_time = p.get("open_time") or ""
                close_time = p.get("close_time") or ""
                min_price = int(p.get("min_price") or 0)
                max_price = int(p.get("max_price") or 0)
                rating = float(p.get("rating") or 0.0)
                reviews_count = int(p.get("reviews_count") or 0)
                peak_hours = p.get("peak_hours") or ""
                best_review = p.get("best_review") or ""
                worst_review = p.get("worst_review") or ""
                img = p.get("image_url") or None
                tags = p.get("tags", "nhom_ban,di_1_minh")
                is_verified = 1

                places_to_insert.append((
                    name, category, addr, district, lat, lon, open_time, close_time,
                    min_price, max_price, rating, reviews_count, peak_hours,
                    best_review, worst_review, img, tags, is_verified
                ))

    if places_to_insert:
        cursor.executemany("""
        INSERT INTO places (
            name, category, address, district, lat, lon, open_time, close_time,
            min_price, max_price, rating, reviews_count, peak_hours,
            best_review, worst_review, image_url, tags, is_verified
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, places_to_insert)
        conn.commit()


def seed_tags_if_needed(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM tags")
    if cursor.fetchone()[0] == 0:
        default_tags = [
            ("nhom_ban", "Nhóm bạn thân", "companion"),
            ("hen_ho", "Cặp đôi / Hẹn hò", "companion"),
            ("gia_dinh", "Gia đình / Người thân", "companion"),
            ("di_1_minh", "Đi một mình (Solo)", "companion"),
        ]
        for k, n, t in default_tags:
            cursor.execute("INSERT OR IGNORE INTO tags (tag_key, name, tier_type) VALUES (?, ?, ?)", (k, n, t))
        conn.commit()

    cursor.execute("SELECT COUNT(*) FROM place_tags")
    if cursor.fetchone()[0] == 0:
        cursor.execute("SELECT id, tag_key FROM tags")
        tag_map = {row[1]: row[0] for row in cursor.fetchall()}

        cursor.execute("SELECT id, tags FROM places")
        places = cursor.fetchall()
        for pid, tags_str in places:
            if not tags_str:
                continue
            raw_tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            for idx, t in enumerate(raw_tags):
                tag_id = tag_map.get(t)
                if tag_id:
                    tier = 1 if idx < 2 else 2
                    cursor.execute("INSERT OR IGNORE INTO place_tags (place_id, tag_id, tier) VALUES (?, ?, ?)", (pid, tag_id, tier))
        conn.commit()

def sync_db_to_json():
    """Tự động đồng bộ toàn bộ địa điểm từ SQLite ra file JSON để mang sang máy khác không bị mất"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM places ORDER BY id ASC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        with open(ENRICHED_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[WARN] sync_db_to_json error:", e)


# ==============================================================================
# THAO TÁC NGƯỜI DÙNG & TÀI KHOẢN (AUTH)
# ==============================================================================

def authenticate_user(username, password):
    """Kiểm tra thông tin đăng nhập với mật khẩu băm SHA-256 an toàn và tự động nâng cấp mật khẩu cũ"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password, full_name, role FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return None
        
    stored_pwd = user["password"]
    if not verify_password(stored_pwd, password):
        conn.close()
        return None
        
    # Tự động nâng cấp mật khẩu cũ dạng plaintext lên băm SHA-256
    if not str(stored_pwd).startswith("sha256:"):
        new_hashed = hash_password(password)
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_hashed, user["id"]))
        conn.commit()
        
    conn.close()
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"]
    }

def register_user(username, password, full_name):
    """Đăng ký tài khoản mới với mật khẩu được băm an toàn theo chuẩn SHA-256"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        hashed_pwd = hash_password(password)
        cursor.execute("INSERT INTO users (username, password, full_name, role) VALUES (?, ?, ?, 'user')", 
                       (username, hashed_pwd, full_name))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return {"id": user_id, "username": username, "full_name": full_name, "role": "user"}
    except sqlite3.IntegrityError:
        conn.close()
        return None

def get_all_users():
    """Lấy danh sách tất cả người dùng trong hệ thống (dành cho Admin)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, full_name, role, created_at FROM users ORDER BY id ASC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def update_user_role(user_id, new_role):
    """Cập nhật vai trò (admin/user) của người dùng"""
    if new_role not in ['admin', 'user']:
        return False, "Vai trò không hợp lệ (chỉ chấp nhận 'admin' hoặc 'user')"
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Kiểm tra xem có phải hạ quyền của admin duy nhất không
    if new_role == 'user':
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = cursor.fetchone()[0]
        cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
        curr = cursor.fetchone()
        if curr and curr['role'] == 'admin' and admin_count <= 1:
            conn.close()
            return False, "Không thể chuyển admin cuối cùng thành user (cần giữ ít nhất 1 admin)"
            
    cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    conn.commit()
    conn.close()
    return True, "Cập nhật vai trò thành công"

def delete_user(user_id):
    """Xóa tài khoản người dùng"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Không cho phép xóa admin duy nhất
    cursor.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    target = cursor.fetchone()
    if not target:
        conn.close()
        return False, "Tài khoản không tồn tại"
        
    if target['role'] == 'admin':
        cursor.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        admin_count = cursor.fetchone()[0]
        if admin_count <= 1:
            conn.close()
            return False, "Không thể xóa admin cuối cùng của hệ thống"
            
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return True, "Xóa tài khoản thành công"



# ==============================================================================
# THAO TÁC ĐỊA ĐIỂM (PLACES CRUD)
# ==============================================================================

def get_all_places(category=None, context_tag=None, min_budget=None, max_budget=None, min_rating=None, search=None, only_verified=True, include_hidden=False):
    """Lấy danh sách địa điểm theo bộ lọc đa chiều (A đến Z)"""
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM places WHERE 1=1"
    params = []

    if not include_hidden:
        query += " AND (is_hidden = 0 OR is_hidden IS NULL)"

    if only_verified:
        query += " AND is_verified = 1"

    if category and category != "all":
        query += " AND category = ?"
        params.append(category)

    if context_tag and context_tag != "all":
        query += " AND tags LIKE ?"
        params.append(f"%{context_tag}%")

    if min_budget and int(min_budget) > 0:
        query += " AND max_price >= ?"
        params.append(int(min_budget))

    if max_budget is not None and str(max_budget).strip() != "":
        max_b_val = int(max_budget)
        if max_b_val == 0:
            query += " AND min_price = 0 AND max_price = 0"
        elif max_b_val > 0:
            query += " AND min_price <= ?"
            params.append(max_b_val)

    if min_rating and float(min_rating) > 0:
        query += " AND rating >= ?"
        params.append(float(min_rating))

    if search:
        s_clean = str(search).strip()
        if s_clean.startswith("#"):
            s_id = s_clean[1:].strip()
            if s_id.isdigit():
                query += " AND id = ?"
                params.append(int(s_id))
            else:
                query += " AND (name LIKE ? OR address LIKE ?)"
                params.extend([f"%{s_clean}%", f"%{s_clean}%"])
        elif s_clean.isdigit():
            # Nếu gõ thuần số (VD: 18), tìm theo ID (khớp chính xác hoặc ID bắt đầu bằng tiền tố số đó)
            query += " AND (id = ? OR CAST(id AS TEXT) LIKE ?)"
            params.extend([int(s_clean), f"{s_clean}%"])
        else:
            query += " AND (name LIKE ? OR address LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY rating DESC, reviews_count DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_place_by_id(place_id):
    """Lấy chi tiết 1 địa điểm"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM places WHERE id = ?", (place_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def sync_place_tags_record(cursor, place_id: int, tags_str: str):
    """Đồng bộ quan hệ N-N giữa place và tags vào bảng place_tags (Section 5 ERD)"""
    if not place_id or not tags_str:
        return
    cursor.execute("SELECT id, tag_key FROM tags")
    tag_map = {row[1]: row[0] for row in cursor.fetchall()}
    if not tag_map:
        return

    cursor.execute("DELETE FROM place_tags WHERE place_id = ?", (place_id,))
    
    t1_list = []
    t2_list = []
    if "tier1:" in tags_str or "tier2:" in tags_str:
        parts = tags_str.split("|")
        for p in parts:
            p = p.strip()
            if p.startswith("tier1:"):
                t1_list = [x.strip() for x in p.replace("tier1:", "").split(",") if x.strip()]
            elif p.startswith("tier2:"):
                t2_list = [x.strip() for x in p.replace("tier2:", "").split(",") if x.strip()]
    else:
        all_tags = [x.strip() for x in tags_str.split(",") if x.strip()]
        t1_list = all_tags[:2]
        t2_list = all_tags[2:]

    for k in t1_list:
        tid = tag_map.get(k)
        if tid:
            cursor.execute("INSERT OR IGNORE INTO place_tags (place_id, tag_id, tier) VALUES (?, ?, 1)", (place_id, tid))
    for k in t2_list:
        tid = tag_map.get(k)
        if tid:
            cursor.execute("INSERT OR IGNORE INTO place_tags (place_id, tag_id, tier) VALUES (?, ?, 2)", (place_id, tid))

def add_place(data):
    """Thêm một địa điểm mới vào CSDL"""
    conn = get_connection()
    cursor = conn.cursor()
    gmaps_val = data.get("google_maps_url")
    if not gmaps_val and data.get("name") and data.get("address"):
        import urllib.parse
        gmaps_val = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(str(data.get('name')) + ' ' + str(data.get('address')))}"

    cursor.execute("""
    INSERT INTO places (
        name, category, address, district, lat, lon, open_time, close_time,
        min_price, max_price, rating, reviews_count, peak_hours,
        best_review, worst_review, image_url, tags, is_verified, is_verified_review, is_admin_choice,
        price_display, hours_display, is_hidden, google_maps_url
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("name"),
        data.get("category", "an_uong"),
        data.get("address") or "TP.HCM",
        data.get("district") or "TP.HCM",
        float(data.get("lat") or 0.0),
        float(data.get("lon") or 0.0),
        data.get("open_time") or "",
        data.get("close_time") or "",
        int(data.get("min_price") or 0),
        int(data.get("max_price") or 0),
        float(data.get("rating")) if (data.get("rating") is not None and str(data.get("rating")).strip() != "") else 0.0,
        int(data.get("reviews_count") or 0),
        data.get("peak_hours") or "",
        data.get("best_review") or "",
        data.get("worst_review") or "",
        data.get("image_url") or None,
        data.get("tags", "nhom_ban"),
        int(data.get("is_verified", 1)),
        int(data.get("is_verified_review", 1)),
        int(data.get("is_admin_choice", 0)),
        data.get("price_display"),
        data.get("hours_display"),
        int(data.get("is_hidden", 0)),
        gmaps_val
    ))
    new_id = cursor.lastrowid
    sync_place_tags_record(cursor, new_id, data.get("tags", "nhom_ban"))
    conn.commit()
    conn.close()
    sync_db_to_json()
    return get_place_by_id(new_id)

def update_place(place_id, data):
    """Cập nhật thông tin địa điểm đã có trong SQLite"""
    existing = get_place_by_id(place_id)
    if not existing:
        return None

    raw_img = data.get("image_url")
    img_val = raw_img.strip() if raw_img and str(raw_img).strip() else None

    conn = get_connection()
    cursor = conn.cursor()
    gmaps_val = data.get("google_maps_url", existing.get("google_maps_url"))
    if not gmaps_val and data.get("name") and data.get("address"):
        import urllib.parse
        gmaps_val = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(str(data.get('name')) + ' ' + str(data.get('address')))}"

    cursor.execute("""
    UPDATE places SET
        name = ?, category = ?, address = ?, district = ?,
        lat = ?, lon = ?, open_time = ?, close_time = ?,
        min_price = ?, max_price = ?, rating = ?, reviews_count = ?,
        peak_hours = ?, best_review = ?, worst_review = ?,
        image_url = ?, tags = ?, is_verified = ?, is_verified_review = ?,
        is_admin_choice = ?, price_display = ?, hours_display = ?, is_hidden = ?,
        google_maps_url = ?
    WHERE id = ?
    """, (
        data.get("name", existing.get("name")),
        data.get("category", existing.get("category")),
        data.get("address", existing.get("address")),
        data.get("district", existing.get("district", "TP.HCM")),
        float(data.get("lat") if data.get("lat") is not None else existing.get("lat", 0.0)),
        float(data.get("lon") if data.get("lon") is not None else existing.get("lon", 0.0)),
        data.get("open_time", existing.get("open_time")),
        data.get("close_time", existing.get("close_time")),
        int(data.get("min_price") if data.get("min_price") is not None else existing.get("min_price", 0)),
        int(data.get("max_price") if data.get("max_price") is not None else existing.get("max_price", 0)),
        float(data.get("rating")) if (data.get("rating") is not None and str(data.get("rating")).strip() != "") else existing.get("rating"),
        int(data.get("reviews_count") if data.get("reviews_count") is not None else existing.get("reviews_count", 0)),
        data.get("peak_hours", existing.get("peak_hours", "")) or "",
        data.get("best_review", existing.get("best_review", "")) or "",
        data.get("worst_review", existing.get("worst_review", "")) or "",
        img_val,
        data.get("tags", existing.get("tags", "nhom_ban")),
        int(data.get("is_verified", existing.get("is_verified", 1))),
        int(data.get("is_verified_review", existing.get("is_verified_review", 1))),
        int(data.get("is_admin_choice", existing.get("is_admin_choice", 0))),
        data.get("price_display", existing.get("price_display")),
        data.get("hours_display", existing.get("hours_display")),
        int(data.get("is_hidden", existing.get("is_hidden", 0))),
        gmaps_val,
        place_id
    ))
    sync_place_tags_record(cursor, place_id, data.get("tags", existing.get("tags", "nhom_ban")))
    conn.commit()
    conn.close()
    sync_db_to_json()
    return get_place_by_id(place_id)

def delete_place(place_id):
    """Xóa một địa điểm và toàn bộ dữ liệu phụ thuộc (Itinerary Stops, Place Tags)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM itinerary_stops WHERE place_id = ?", (place_id,))
    cursor.execute("DELETE FROM place_tags WHERE place_id = ?", (place_id,))
    cursor.execute("DELETE FROM places WHERE id = ?", (place_id,))
    conn.commit()
    conn.close()
    sync_db_to_json()
    return True

def toggle_hide_place(place_id):
    """Bật / tắt trạng thái ẩn của địa điểm (Admin Soft Hide)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, is_hidden FROM places WHERE id = ?", (place_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    curr_hidden = row["is_hidden"] if row["is_hidden"] is not None else 0
    new_hidden = 1 if curr_hidden == 0 else 0
    cursor.execute("UPDATE places SET is_hidden = ? WHERE id = ?", (new_hidden, place_id))
    conn.commit()
    conn.close()
    sync_db_to_json()
    return {"id": place_id, "is_hidden": new_hidden}



# ==============================================================================
# NHẬP XUẤT CSV (IMPORT / EXPORT)
# ==============================================================================

def generate_sample_csv():
    """Tạo nội dung file CSV mẫu chuẩn cho Admin tải về điền (an toàn tuyệt đối với mọi dấu phẩy)"""
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow([
        "name", "category", "address", "open_time", "close_time", 
        "min_price", "max_price", "rating", "reviews_count", "peak_hours",
        "best_review", "worst_review", "tags", "lat", "lon", "google_maps_url"
    ])
    writer.writerow([
        "Hủ Tiếu Nam Vang Triều Châu", "an_uong", "85 Trần Bình Trọng, Phường 1, Quận 5", "06:30", "22:00",
        40000, 75000, 4.6, 820, "18:00 - 19:30",
        "Nước dùng ngọt xương tự nhiên, sườn mềm tôm tươi", "Quán giờ tan tầm hơi đông", "nhom_ban,di_1_minh", 10.7570, 106.6780,
        "https://www.google.com/maps/search/?api=1&query=H%E1%BB%A7+Ti%E1%BA%BFu+Nam+Vang+Tri%E1%BB%81u+Ch%C3%A2u+Qu%E1%BA%ADn+5"
    ])
    writer.writerow([
        "Cà Phê Trầm Chợ Lớn", "di_choi", "142 Triệu Quang Phục, Phường 11, Quận 5", "08:00", "22:30",
        35000, 65000, 4.5, 430, "15:00 - 17:00",
        "Không gian hoài cổ, nhạc nhẹ, rất hợp học bài và hẹn hò", "Hẻm hơi nhỏ", "hen_ho,di_1_minh", 10.7540, 106.6610,
        "https://www.google.com/maps/search/?api=1&query=C%C3%A0+Ph%C3%AA+Tr%E1%BA%A7m+Ch%E1%BB%A3+L%E1%BB%9Bn+Qu%E1%BA%ADn+5"
    ])
    return output.getvalue()

def generate_sample_excel():
    """Tạo nội dung file Excel (.xlsx) mẫu chuẩn cho Admin tải về nạp dữ liệu (G6-FR09)"""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DS_Dia_Diem_Mau"

    headers = [
        "name", "category", "address", "open_time", "close_time", 
        "min_price", "max_price", "rating", "reviews_count", "peak_hours",
        "best_review", "worst_review", "tags", "lat", "lon", "google_maps_url"
    ]
    ws.append(headers)

    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="E11D48", end_color="E11D48", fill_type="solid")
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    sample_rows = [
        [
            "Hủ Tiếu Nam Vang Triều Châu", "an_uong", "85 Trần Bình Trọng, Phường 1, Quận 5", "06:30", "22:00",
            40000, 75000, 4.6, 820, "18:00 - 19:30",
            "Nước dùng ngọt xương tự nhiên, sườn mềm tôm tươi", "Quán giờ tan tầm hơi đông", "nhom_ban,di_1_minh", 10.7570, 106.6780,
            "https://www.google.com/maps/search/?api=1&query=H%E1%BB%A7+Ti%E1%BA%BFu+Nam+Vang+Tri%E1%BB%81u+Ch%C3%A2u+Qu%E1%BA%ADn+5"
        ],
        [
            "Cà Phê Trầm Chợ Lớn", "di_choi", "142 Triệu Quang Phục, Phường 11, Quận 5", "08:00", "22:30",
            35000, 65000, 4.5, 430, "15:00 - 17:00",
            "Không gian hoài cổ, nhạc nhẹ, rất hợp học bài và hẹn hò", "Hẻm hơi nhỏ", "hen_ho,di_1_minh", 10.7540, 106.6610,
            "https://www.google.com/maps/search/?api=1&query=C%C3%A0+Ph%C3%AA+Tr%E1%BA%A7m+Ch%E1%BB%A3+L%E1%BB%9Bn+Qu%E1%BA%ADn+5"
        ]
    ]
    for r in sample_rows:
        ws.append(r)

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = col[0].column_letter
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_rows_from_file_content(data, filename: str):
    """
    Tự động nhận diện định dạng CSV hoặc Excel (.xlsx, .xls) và trích xuất danh sách row dictionaries
    """
    fname_lower = filename.lower()
    is_excel = fname_lower.endswith(".xlsx") or fname_lower.endswith(".xls")

    if is_excel or (isinstance(data, str) and ("base64," in data or (len(data) > 100 and "\n" not in data[:100] and "\r" not in data[:100]))):
        import openpyxl
        import base64
        file_bytes = data
        if isinstance(data, str):
            if "base64," in data:
                data = data.split("base64,")[1]
            try:
                file_bytes = base64.b64decode(data)
            except Exception:
                file_bytes = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray)):
            file_bytes = data

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        raw_rows = list(sheet.iter_rows(values_only=True))
        if not raw_rows:
            return []

        header_row = raw_rows[0]
        headers = [str(h).strip().lower() if h is not None else f"col_{i}" for i, h in enumerate(header_row)]

        parsed_rows = []
        for r in raw_rows[1:]:
            if not any(val is not None and str(val).strip() != "" for val in r):
                continue
            row_dict = {}
            for i, val in enumerate(r):
                if i < len(headers):
                    key = headers[i]
                    row_dict[key] = "" if val is None else str(val).strip()
            parsed_rows.append(row_dict)
        return parsed_rows
    else:
        csv_str = data if isinstance(data, str) else data.decode("utf-8-sig", errors="replace")
        csv_str = csv_str.lstrip("\ufeff")
        f = io.StringIO(csv_str)
        reader = csv.DictReader(f)
        return list(reader)


def import_file_data(data, filename="uploaded_places.csv"):
    """
    Đọc dữ liệu từ file CSV hoặc Excel (.xlsx) tải lên và nạp vào CSDL với kiểm tra lỗi chặt chẽ (G6-FR09 & Business Rule 4):
    - Phát hiện trường bắt buộc bị thiếu (Tên quán, Thể loại, Địa chỉ)
    - Phát hiện kiểu dữ liệu sai (Tọa độ không phải float, Giá tiền không phải số nguyên, Sao không hợp lệ)
    - Ghi nhận chi tiết dòng lỗi để Admin xem và chỉnh sửa (Demo Flow 3)
    - Ghi log lịch sử import vào bảng import_logs (Section 5)
    """
    parsed_rows = parse_rows_from_file_content(data, filename)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, category, address, lat, lon, google_maps_url FROM places")
    existing_places = [dict(r) for r in cursor.fetchall()]

    success_count = 0
    errors = []
    row_idx = 1  # Header là dòng 1, dòng dữ liệu đầu tiên là dòng 2

    for row in parsed_rows:
        row_idx += 1
        name = sanitize_cell_value((row.get("name") or "").strip())
        address = sanitize_cell_value((row.get("address") or "").strip())
        category = sanitize_cell_value((row.get("category") or "").strip().lower())

        # 1. Kiểm tra trường bắt buộc và độ dài
        if not name or len(name) < 2:
            errors.append({"row": row_idx, "field": "name", "reason": "Tên địa điểm phải có ít nhất 2 ký tự (trường bắt buộc)"})
            continue

        if not address or len(address) < 5:
            errors.append({"row": row_idx, "field": "address", "reason": f"Quán '{name}' thiếu địa chỉ cụ thể hoặc địa chỉ quá ngắn (tối thiểu 5 ký tự)"})
            continue

        if category not in ["an_uong", "di_choi"]:
            errors.append({"row": row_idx, "field": "category", "reason": f"Quán '{name}' có thể loại '{category}' không hợp lệ (phải là 'an_uong' hoặc 'di_choi')"})
            continue

        # 2. Kiểm tra kiểu dữ liệu tọa độ
        lat_raw = row.get("lat")
        if lat_raw is None or str(lat_raw).strip() == "":
            errors.append({"row": row_idx, "field": "lat", "reason": f"Quán '{name}' thiếu tọa độ vĩ độ (lat)"})
            continue
        try:
            lat = float(lat_raw)
            if not (10.3 <= lat <= 11.2):
                raise ValueError("Vĩ độ ngoài phạm vi TP.HCM (10.3 - 11.2)")
        except Exception as e:
            errors.append({"row": row_idx, "field": "lat", "reason": f"Quán '{name}': Vĩ độ (lat) '{lat_raw}' không hợp lệ ({str(e)})"})
            continue

        lon_raw = row.get("lon")
        if lon_raw is None or str(lon_raw).strip() == "":
            errors.append({"row": row_idx, "field": "lon", "reason": f"Quán '{name}' thiếu tọa độ kinh độ (lon)"})
            continue
        try:
            lon = float(lon_raw)
            if not (106.3 <= lon <= 107.2):
                raise ValueError("Kinh độ ngoài phạm vi TP.HCM (106.3 - 107.2)")
        except Exception as e:
            errors.append({"row": row_idx, "field": "lon", "reason": f"Quán '{name}': Kinh độ (lon) '{lon_raw}' không hợp lệ ({str(e)})"})
            continue

        # 3. Kiểm tra kiểu dữ liệu mức giá (không mock giá nếu trống)
        try:
            min_price = int(float(row.get("min_price"))) if (row.get("min_price") is not None and str(row.get("min_price")).strip() != "") else 0
            if min_price < 0:
                raise ValueError("Giá âm")
        except Exception:
            errors.append({"row": row_idx, "field": "min_price", "reason": f"Quán '{name}': Giá tối thiểu (min_price) '{row.get('min_price')}' phải là số nguyên >= 0"})
            continue

        try:
            max_price = int(float(row.get("max_price"))) if (row.get("max_price") is not None and str(row.get("max_price")).strip() != "") else 0
            if max_price < min_price and max_price > 0:
                raise ValueError("max_price < min_price")
        except Exception:
            errors.append({"row": row_idx, "field": "max_price", "reason": f"Quán '{name}': Giá tối đa (max_price) '{row.get('max_price')}' phải lớn hơn hoặc bằng giá tối thiểu"})
            continue

        # 4. Kiểm tra số sao đánh giá (không mock 4.5 sao nếu trống)
        try:
            rating = float(row.get("rating")) if (row.get("rating") is not None and str(row.get("rating")).strip() != "") else 0.0
            if not (0.0 <= rating <= 5.0):
                raise ValueError("Rating ngoài 0-5")
        except Exception:
            errors.append({"row": row_idx, "field": "rating", "reason": f"Quán '{name}': Đánh giá sao (rating) '{row.get('rating')}' phải trong khoảng 0.0 đến 5.0"})
            continue

        try:
            reviews_count = int(float(row.get("reviews_count"))) if (row.get("reviews_count") is not None and str(row.get("reviews_count")).strip() != "") else 0
        except Exception:
            reviews_count = 0

        gmaps_url = (row.get("google_maps_url") or row.get("maps_url") or "").strip()
        if not gmaps_url:
            import urllib.parse
            gmaps_url = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(name + ' ' + address)}"

        # Kiểm tra trùng lặp đa lớp thông minh (Tên, Link Maps, Địa chỉ, GPS < 25m)
        dup_reason = find_duplicate_place(name, address, lat, lon, gmaps_url, category, existing_places)
        if dup_reason:
            errors.append({"row": row_idx, "field": "name", "reason": f"Địa điểm '{name}' đã tồn tại trong CSDL ({dup_reason})"})
            continue

        cursor.execute("""
        INSERT INTO places (
            name, category, address, district, lat, lon, open_time, close_time,
            min_price, max_price, rating, reviews_count, peak_hours,
            best_review, worst_review, image_url, tags, is_verified, is_hidden, google_maps_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)
        """, (
            name,
            category,
            address,
            row.get("district") or "TP.HCM",
            lat,
            lon,
            row.get("open_time") or "",
            row.get("close_time") or "",
            min_price,
            max_price,
            rating,
            reviews_count,
            row.get("peak_hours") or "",
            row.get("best_review") or "",
            row.get("worst_review") or "",
            row.get("image_url") or None,
            row.get("tags") or "nhom_ban",
            gmaps_url
        ))
        existing_places.append({
            "name": name,
            "category": category,
            "address": address,
            "lat": lat,
            "lon": lon,
            "google_maps_url": gmaps_url
        })
        success_count += 1

    total_rows = (row_idx - 1)
    error_count = len(errors)

    # Ghi log lịch sử import vào CSDL (Section 5)
    try:
        cursor.execute("""
        INSERT INTO import_logs (filename, total_rows, success_count, error_count, error_details_json)
        VALUES (?, ?, ?, ?, ?)
        """, (filename, total_rows, success_count, error_count, json.dumps(errors, ensure_ascii=False)))
    except Exception as e:
        print("[WARN] Failed to insert import_log:", e)

    conn.commit()
    conn.close()
    sync_db_to_json()
    return {
        "filename": filename,
        "total_rows": total_rows,
        "success_count": success_count,
        "error_count": error_count,
        "errors": errors
    }


def import_csv_data(csv_text, filename="uploaded_places.csv"):
    """Wrapper tương thích ngược cho import CSV"""
    return import_file_data(csv_text, filename=filename)


def import_excel_data(excel_data, filename="uploaded_places.xlsx"):
    """Wrapper chuyên dụng cho import Excel (.xlsx)"""
    return import_file_data(excel_data, filename=filename)


def save_itinerary(itin_data, stops_data):
    """Lưu lịch trình và các chặng dừng vào CSDL (Section 5 ERD)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO itineraries (
        user_id, start_location, start_lat, start_lon, free_time, companion,
        purpose, budget_level, target_budget, total_estimated_budget_min,
        total_estimated_budget_max, total_duration_minutes, summary
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        itin_data.get("user_id"),
        itin_data.get("start_location"),
        itin_data.get("start_lat"),
        itin_data.get("start_lon"),
        itin_data.get("free_time"),
        itin_data.get("companion", "ban_be"),
        itin_data.get("purpose", "ca_hai"),
        itin_data.get("budget_level", "100k_250k"),
        itin_data.get("target_budget", 250000),
        itin_data.get("total_estimated_budget_min", 0),
        itin_data.get("total_estimated_budget_max", 0),
        itin_data.get("total_duration_minutes", 0),
        itin_data.get("summary", "")
    ))
    itin_id = cursor.lastrowid

    for s in stops_data:
        cursor.execute("""
        INSERT INTO itinerary_stops (
            itinerary_id, place_id, stop_order, time_slot, action_title,
            travel_distance_km, travel_time_minutes, estimated_cost_min, estimated_cost_max
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            itin_id,
            s.get("place_id"),
            s.get("stop_order", 1),
            s.get("time_slot", ""),
            s.get("action_title", ""),
            s.get("travel_distance_km", 0.0),
            s.get("travel_time_minutes", 0),
            s.get("estimated_cost_min", 0),
            s.get("estimated_cost_max", 0)
        ))

    conn.commit()
    conn.close()
    return itin_id

def get_import_logs(limit=10):
    """Lấy danh sách lịch sử nạp CSV gần nhất"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM import_logs ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ==========================================
# QUẢN LÝ TAG & BỘ LỌC (G6-FR08 & Section 5 ERD)
# ==========================================
def get_all_tags():
    """Lấy danh sách tất cả các tag cùng số lượng quán liên kết"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT t.id, t.tag_key, t.name, t.tier_type, t.is_active, t.created_at,
           COUNT(pt.place_id) as place_count
    FROM tags t
    LEFT JOIN place_tags pt ON t.id = pt.tag_id
    GROUP BY t.id
    ORDER BY t.tier_type, t.id
    """)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def add_tag(tag_key: str, name: str, tier_type: str = "companion"):
    """Thêm một tag mới vào hệ thống"""
