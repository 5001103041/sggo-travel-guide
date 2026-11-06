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
            "lon": 106.6620,
            "min_price": 20000,
            "max_price": 50000
        })
        p_id = p["id"]

        update_payload = dict(p)
        update_payload["min_price"] = 35000
        update_payload["max_price"] = 75000
        update_payload["open_time"] = "09:00"

        res = self.client.put(f"/api/admin/places/{p_id}", json=update_payload)
        self.assertEqual(res.status_code, 200)
        updated_data = res.json()["place"]
        self.assertEqual(updated_data["min_price"], 35000)
        self.assertEqual(updated_data["max_price"], 75000)

        # Dọn dẹp
        db.delete_place(p_id)

    def test_rtm_fr01_03_delete_place(self):
        """[TEST-FR01-03] Admin xóa địa điểm và kiểm tra xóa vĩnh viễn khỏi SQLite."""
        p = db.add_place({
            "name": "[TEST] Quán Sắp Xóa",
            "category": "di_choi",
            "address": "456 Trần Hưng Đạo",
            "lat": 10.751,
            "lon": 106.661
        })
        p_id = p["id"]

        del_res = self.client.delete(f"/api/admin/places/{p_id}")
        self.assertEqual(del_res.status_code, 200)

        # Kiểm tra quán không còn tồn tại
        check_p = db.get_place_by_id(p_id)
        self.assertIsNone(check_p)

    def test_rtm_fr01_04_toggle_hide_place(self):
        """[TEST-FR01-04] Admin ẩn quán (is_hidden = 1) và bật lại (is_hidden = 0)."""
        p = db.add_place({
            "name": "[TEST] Quán Ẩn Hiện",
            "category": "an_uong",
            "address": "12 Đỗ Ngọc Thạnh",
            "is_hidden": 0
        })
        p_id = p["id"]

        # Toggle ẩn lần 1 -> is_hidden = 1
        res1 = self.client.post(f"/api/admin/places/{p_id}/toggle-hide")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["place"]["is_hidden"], 1)

        # Toggle ẩn lần 2 -> is_hidden = 0
        res2 = self.client.post(f"/api/admin/places/{p_id}/toggle-hide")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["place"]["is_hidden"], 0)

        db.delete_place(p_id)

    # ==========================================================================
    # NHÓM 2: G6-FR02 - TÌM KIẾM & BỘ LỌC ĐA CHIỀU (RIÊNG LẺ & KẾT HỢP)
    # ==========================================================================

    def test_rtm_fr02_01_filter_category_an_uong(self):
        """[TEST-FR02-01] Lọc theo thể loại 'an_uong': 100% kết quả trả về phải là ẩm thực."""
        res = self.client.get("/api/places?category=an_uong")
        self.assertEqual(res.status_code, 200)
        places = res.json() if isinstance(res.json(), list) else res.json().get("places", [])
        self.assertGreater(len(places), 0)
        for p in places:
            self.assertEqual(p["category"], "an_uong")

    def test_rtm_fr02_02_filter_category_di_choi(self):
        """[TEST-FR02-02] Lọc theo thể loại 'di_choi': 100% kết quả là điểm đến tham quan."""
        res = self.client.get("/api/places?category=di_choi")
        self.assertEqual(res.status_code, 200)
        places = res.json() if isinstance(res.json(), list) else res.json().get("places", [])
        self.assertGreater(len(places), 0)
        for p in places:
            self.assertEqual(p["category"], "di_choi")

    def test_rtm_fr02_03_filter_context_tag(self):
        """[TEST-FR02-03] Lọc theo ngữ cảnh tag 'di_1_minh'."""
        res = self.client.get("/api/places?tag=di_1_minh")
        self.assertEqual(res.status_code, 200)
        places = res.json() if isinstance(res.json(), list) else res.json().get("places", [])
        self.assertGreater(len(places), 0)
        for p in places:
            self.assertIn("di_1_minh", p.get("tags", ""))

    def test_rtm_fr02_04_filter_price_range(self):
        """[TEST-FR02-04] Lọc theo khoảng giá từ 50.000đ đến 100.000đ."""
        res = self.client.get("/api/places?min_price=50000&max_price=100000")
        self.assertEqual(res.status_code, 200)
        places = res.json() if isinstance(res.json(), list) else res.json().get("places", [])
        self.assertGreater(len(places), 0)
        for p in places:
            self.assertTrue(p["min_price"] <= 100000 and p["max_price"] >= 50000)

    def test_rtm_fr02_05_filter_combined_category_and_price(self):
        """[TEST-FR02-05] Lọc kết hợp: Thể loại 'di_choi' + Miễn phí (max_price = 0)."""
        res = self.client.get("/api/places?category=di_choi&max_price=0")
        self.assertEqual(res.status_code, 200)
        places = res.json() if isinstance(res.json(), list) else res.json().get("places", [])
        self.assertGreater(len(places), 0)
        for p in places:
            self.assertEqual(p["category"], "di_choi")
            self.assertEqual(p["max_price"], 0)

    def test_rtm_fr02_06_search_by_keyword(self):
        """[TEST-FR02-06] Tìm kiếm địa điểm theo từ khóa tên quán hoặc tên đường."""
        res = self.client.get("/api/places?search=Thiên Hậu")
        self.assertEqual(res.status_code, 200)
        places = res.json() if isinstance(res.json(), list) else res.json().get("places", [])
        self.assertGreater(len(places), 0)
        self.assertTrue(any("Thiên Hậu" in p["name"] for p in places))

    def test_rtm_fr02_07_search_by_id_pure_numeric(self):
        """[TEST-FR02-07] Tìm kiếm thuần số ID (18 hoặc #18) chỉ khớp ID quán, không lẫn số nhà đường."""
        # 1. Tìm thuần số '18': Chỉ trả về ID 18 hoặc bắt đầu bằng 18 (180..189), không lẫn quán có số nhà 18, 118...
        res_numeric = self.client.get("/api/places?search=18")
        self.assertEqual(res_numeric.status_code, 200)
        places_18 = res_numeric.json() if isinstance(res_numeric.json(), list) else res_numeric.json().get("places", [])
        ids_18 = [p["id"] for p in places_18]
        self.assertIn(18, ids_18)
        self.assertNotIn(126, ids_18, "Không được lẫn ID 126 (chỉ vì số nhà là 118 Hồ Tùng Mậu)")
        self.assertNotIn(139, ids_18, "Không được lẫn ID 139 (chỉ vì số nhà là 18 Tú Xương)")
        for pid in ids_18:
            self.assertTrue(str(pid).startswith("18"), f"Tất cả kết quả phải có ID bắt đầu bằng 18, thực tế: {pid}")

        # 2. Tìm chính xác '#18': Chỉ trả về duy nhất ID 18
        res_hash = self.client.get("/api/places?search=%2318")
        self.assertEqual(res_hash.status_code, 200)
        places_hash = res_hash.json() if isinstance(res_hash.json(), list) else res_hash.json().get("places", [])
        ids_hash = [p["id"] for p in places_hash]
        self.assertEqual(ids_hash, [18], "Tìm kiếm '#18' phải khớp chính xác duy nhất quán có ID 18")

    # ==========================================================================
    # NHÓM 3: G6-FR03 - NGƯỜI DÙNG NHẬP VỊ TRÍ, THỜI GIAN, NGÂN SÁCH, SỞ THÍCH
    # ==========================================================================

    def test_rtm_fr03_01_start_location_and_free_time(self):
        """[TEST-FR03-01] Nhập vị trí toạ độ GPS, giờ rảnh, ngân sách và sở thích."""
        payload = {
            "start_location": "Đại học Sư Phạm TP.HCM",
            "start_lat": 10.7601,
            "start_lon": 106.6823,
            "free_time": "14:00 - 18:30",
            "companion": "ban_be",
            "purpose": "ca_hai",
            "budget_level": "100k_250k",
            "target_budget": 250000,
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("feasible"))
        self.assertEqual(len(data.get("steps", [])), 3)

    def test_rtm_fr03_02_start_location_landmark_coordinates(self):
        """[TEST-FR03-02] Hệ thống tự động phân giải toạ độ từ tên mốc địa danh chuẩn."""
        lat, lon = resolve_start_coords("Chợ Bến Thành, Quận 1")
        self.assertAlmostEqual(lat, 10.7725, places=2)
        self.assertAlmostEqual(lon, 106.6980, places=2)

    # ==========================================================================
    # NHÓM 4: G6-FR04 & G6-FR07 - THUẬT TOÁN ĐỊNH TUYẾN HEURISTIC & BẢN ĐỒ
    # ==========================================================================

    def test_rtm_fr04_01_nearest_neighbor_ordering(self):
        """[TEST-FR04-01] Thuật toán Nearest Neighbor TSP sắp xếp thứ tự các trạm tối ưu."""
        start = (10.7500, 106.6500)
        pool = [
            {"id": 1, "name": "Điểm Xa", "lat": 10.7900, "lon": 106.7000},
            {"id": 2, "name": "Điểm Rất Gần", "lat": 10.7505, "lon": 106.6505},
            {"id": 3, "name": "Điểm Vừa", "lat": 10.7600, "lon": 106.6600}
        ]
        route = optimize_route_nearest_neighbor(start, pool, max_stops=3)
        self.assertEqual(len(route), 3)
        self.assertEqual(route[0]["id"], 2, "Trạm 1 phải là điểm gần xuất phát nhất")
        self.assertEqual(route[1]["id"], 3, "Trạm 2 phải là điểm láng giềng kế tiếp")
        self.assertEqual(route[2]["id"], 1, "Trạm 3 là điểm xa nhất")

    def test_rtm_fr04_02_haversine_distance_accuracy(self):
        """[TEST-FR04-02] Tính toán khoảng cách Haversine giữa 2 tọa độ GPS chuẩn xác."""
        # Chợ Bến Thành (10.7725, 106.6980) đến Nhà Thờ Đức Bà (10.7798, 106.6990) ~ 0.82 km
        d = calculate_haversine_distance(10.7725, 106.6980, 10.7798, 106.6990)
        self.assertTrue(0.7 <= d <= 1.0, f"Khoảng cách tính toán ({d} km) nằm ngoài sai số cho phép")

    def test_rtm_fr07_01_gmaps_multi_stop_url_generated(self):
        """[TEST-FR07-01] Tạo link Google Maps Multi-stop hai bánh (travelmode=two_wheeler)."""
        payload = {
            "start_location": "280 An Dương Vương, TP.HCM",
            "free_time": "14:00 - 18:30",
            "purpose": "ca_hai",
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
