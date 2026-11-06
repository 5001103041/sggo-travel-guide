# -*- coding: utf-8 -*-
"""
DỰ ÁN SGGO! - HỆ THỐNG GỢI Ý ĐỊA ĐIỂM & LẬP LỊCH TRÌNH THÔNG MINH
BỘ KIỂM THỬ TOÀN DIỆN (AUTOMATED TEST SUITE & RTM VERIFICATION)
Môn học: Nhập Môn Công Nghệ Phần Mềm - Nhóm 6
Tuân thủ 100% tài liệu Yêu cầu đề tài & Ma trận Truy xuất RTM (25 Test Cases)
"""

import unittest
import json
import sqlite3
import os
import sys

# Đảm bảo mã hóa UTF-8 cho môi trường console Windows
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Thêm thư mục gốc vào sys.path để import backend modules
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi.testclient import TestClient
from backend.main import (
    app, calculate_haversine_distance, optimize_route_nearest_neighbor,
    resolve_start_coords, parse_free_time_minutes
)
import backend.database as db


class TestSGGoTestSuite(unittest.TestCase):
    """
    Tập hợp 25 Test Cases tự động đạt chuẩn kiểm thử phần mềm SE,
    liên kết trực quan với từng mã Requirement trong RTM.
    """

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, headers={"X-User-Role": "admin"})
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM places WHERE name LIKE '[TEST]%'")
            c.execute("SELECT MAX(id) FROM places")
            row = c.fetchone()
            max_id = (row[0] if row and row[0] is not None else 201)
            c.execute("UPDATE sqlite_sequence SET seq = ? WHERE name = 'places'", (max_id,))
            conn.commit()

    # ==========================================================================
    # NHÓM 1: G6-FR01 & G6-FR08 - QUẢN LÝ ĐỊA ĐIỂM (CRUD & ẨN/HIỆN QUÁN)
    # ==========================================================================

    def test_rtm_fr01_01_create_place(self):
        """[TEST-FR01-01] Admin thêm địa điểm mới vào CSDL SQLite thành công."""
        payload = {
            "name": "[TEST] Quán Mới Tạo AutoTest",
            "category": "an_uong",
            "address": "123 Đường Test, Quận 5",
            "district": "Quận 5",
            "lat": 10.7550,
            "lon": 106.6650,
            "open_time": "08:00",
            "close_time": "22:00",
            "min_price": 30000,
            "max_price": 60000,
            "rating": 4.6,
            "reviews_count": 120,
            "tags": "di_1_minh,nhom_ban",
            "is_verified": 1,
            "is_hidden": 0
        }
        res = self.client.post("/api/admin/places", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("status"), "ok")
        created_p = data.get("place")
        self.assertIsNotNone(created_p)
        self.assertEqual(created_p["name"], payload["name"])

        # Dọn dẹp bản ghi test
        if created_p.get("id"):
            db.delete_place(created_p["id"])

    def test_rtm_fr01_02_update_place(self):
        """[TEST-FR01-02] Admin cập nhật giá, giờ mở cửa và tag của địa điểm."""
        # Tạo trước một bản ghi
        p = db.add_place({
            "name": "[TEST] Quán Để Update",
            "category": "an_uong",
            "address": "999 Nguyễn Trãi, Quận 5",
            "district": "Quận 5",
            "lat": 10.7520,
