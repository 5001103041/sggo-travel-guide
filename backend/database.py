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
