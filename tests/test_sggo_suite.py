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
        self.assertEqual(res.status_code, 200)
        data = res.json()
        gmaps_url = data.get("gmaps_multi_url", "")
        self.assertIn("https://www.google.com/maps/dir/?api=1", gmaps_url)
        self.assertIn("waypoints=", gmaps_url)
        self.assertIn("travelmode=two_wheeler", gmaps_url)

    def test_rtm_fr07_02_timeline_steps_have_travel_distance_and_time(self):
        """[TEST-FR07-02] Mỗi chặng trong Timeline có ước tính cự ly km và số phút di chuyển."""
        payload = {
            "start_location": "Chợ Bến Thành, Quận 1",
            "free_time": "14:00 - 18:30",
            "purpose": "an_uong",
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        self.assertEqual(res.status_code, 200)
        steps = res.json().get("steps", [])
        for s in steps:
            self.assertIn("Di chuyển ~", s.get("travel_info", ""))
            self.assertIn("phút xe máy", s.get("travel_info", ""))

    # ==========================================================================
    # NHÓM 5: G6-FR05 - KIỂM TRA TỔNG NGÂN SÁCH & KHOẢNG THỜI GIAN CHO PHÉP
    # ==========================================================================

    def test_rtm_fr05_01_budget_constraint_checked(self):
        """[TEST-FR05-01] Lịch trình kiểm tra tổng chi phí ước tính nằm trong ràng buộc."""
        payload = {
            "start_location": "Chợ Bến Thành",
            "free_time": "14:00 - 18:30",
            "purpose": "an_uong",
            "budget_level": "100k_250k",
            "target_budget": 250000,
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        data = res.json()
        self.assertTrue(data.get("feasible"))
        kpi = data.get("kpi", {})
        self.assertIn("total_min_cost", kpi)
        self.assertIn("total_max_cost", kpi)
        self.assertIn("is_within_budget", kpi)
        self.assertGreater(kpi["total_max_cost"], 0)

    def test_rtm_fr05_02_duration_constraint_checked(self):
        """[TEST-FR05-02] Lịch trình kiểm tra tổng thời gian (di chuyển + trải nghiệm)."""
        payload = {
            "start_location": "Chợ Bến Thành",
            "free_time": "14:00 - 18:30",
            "purpose": "ca_hai",
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        data = res.json()
        kpi = data.get("kpi", {})
        self.assertIn("total_duration_minutes", kpi)
        self.assertIn("free_duration_minutes", kpi)
        self.assertIn("is_within_time", kpi)
        self.assertEqual(kpi["free_duration_minutes"], 270)
        self.assertTrue(kpi["is_within_time"])

    # ==========================================================================
    # NHÓM 6: BUSINESS RULE 3 - BÁO ĐIỀU KIỆN KHÔNG THỎA & ĐỀ XUẤT NỚI ĐIỀU KIỆN
    # ==========================================================================

    def test_rtm_br03_01_time_too_short_reported_with_relaxation_suggestion(self):
        """[TEST-BR03-01] Thời gian rảnh quá ngắn (<60 phút) -> Báo lỗi TIME_TOO_SHORT kèm đề xuất nới."""
        payload = {
            "start_location": "Chợ Bến Thành",
            "free_time": "18:00 - 18:30",  # Chỉ có 30 phút rảnh
            "purpose": "ca_hai",
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        data = res.json()
        self.assertFalse(data.get("feasible"))
        self.assertEqual(data.get("error_code"), "TIME_TOO_SHORT")
        self.assertIn("quá ngắn", data.get("message", ""))
        self.assertIn("suggestion", data)
        self.assertEqual(data.get("recommended_time"), "14:00 - 18:30")

    def test_rtm_br03_02_budget_too_low_reported_with_relaxation_suggestion(self):
        """[TEST-BR03-02] Ngân sách ăn uống quá thấp (<40.000đ) -> Báo lỗi BUDGET_TOO_LOW kèm đề xuất nới."""
        payload = {
            "start_location": "Chợ Bến Thành",
            "free_time": "14:00 - 18:30",
            "purpose": "an_uong",
            "budget_level": "custom",
            "target_budget": 15000,  # 15k không thể ăn 3 trạm
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        data = res.json()
        self.assertFalse(data.get("feasible"))
        self.assertEqual(data.get("error_code"), "BUDGET_TOO_LOW")
        self.assertIn("quá thấp", data.get("message", ""))
        self.assertIn("suggestion", data)
        self.assertEqual(data.get("recommended_budget"), 100000)

    # ==========================================================================
    # NHÓM 7: BUSINESS RULE 2 - ĐỊA ĐIỂM ẨN / ĐÓNG CỬA KHÔNG ĐƯA VÀO LỊCH TRÌNH
    # ==========================================================================

    def test_rtm_br02_01_hidden_place_excluded_from_itinerary(self):
        """[TEST-BR02-01] Quán bị ẩn (is_hidden=1) TUYỆT ĐỐI KHÔNG xuất hiện trong lịch trình."""
        # Thêm quán test bị ẩn ngay sát điểm xuất phát
        p = db.add_place({
            "name": "[TEST] Quán Rất Gần Nhưng Bị Ẩn",
            "category": "an_uong",
            "address": "1 An Dương Vương, Quận 5",
            "lat": 10.7602,
            "lon": 106.6824,
            "is_hidden": 1
        })
        p_id = p["id"]

        payload = {
            "start_location": "280 An Dương Vương, TP.HCM",
            "start_lat": 10.7601,
            "start_lon": 106.6823,
            "free_time": "14:00 - 18:30",
            "purpose": "an_uong",
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        data = res.json()
        steps = data.get("steps", [])
        place_ids = [s.get("place_id") for s in steps]
        self.assertNotIn(p_id, place_ids, "Địa điểm bị ẩn không được phép đưa vào lịch trình")

        db.delete_place(p_id)

    def test_rtm_br02_02_hidden_place_excluded_from_public_search(self):
        """[TEST-BR02-02] Quán bị ẩn không xuất hiện trong API tìm kiếm công khai."""
        p = db.add_place({
            "name": "[TEST] Quán Bí Mật Bị Ẩn Khỏi Tìm Kiếm",
            "category": "an_uong",
            "address": "123 Quận 5",
            "is_hidden": 1
        })
        p_id = p["id"]

        res = self.client.get("/api/places?search=Quán Bí Mật Bị Ẩn")
        places = res.json() if isinstance(res.json(), list) else res.json().get("places", [])
        self.assertEqual(len(places), 0, "Quán bị ẩn không được lộ ra qua API người dùng thông thường")

        db.delete_place(p_id)

    def test_rtm_br02_03_closed_place_excluded_from_itinerary(self):
        """[TEST-BR02-03] Business Rule 2 & 3: Quán đóng cửa tuyệt đối không đưa vào lịch trình, khung giờ đóng cửa báo ALL_PLACES_CLOSED."""
        from backend.main import is_place_open_during_window

        # 1. Khung giờ ban ngày bình thường: Sinh lịch trình khả thi, 100% trạm mở cửa
        payload_day = {
            "start_location": "Chợ Bến Thành, Quận 1",
            "free_time": "14:00 - 18:30",
            "purpose": "ca_hai",
            "ai_model": "rule_based"
        }
        res_day = self.client.post("/api/ai-itinerary", json=payload_day).json()
        self.assertTrue(res_day.get("feasible", False), "Khung giờ ban ngày phải sinh được lịch trình khả thi")
        steps = res_day.get("steps", [])
        self.assertGreaterEqual(len(steps), 3, "Phải có đủ 3 trạm")
        for step in steps:
            pid = step.get("place_id")
            place = db.get_place_by_id(pid)
            self.assertTrue(is_place_open_during_window(place, "14:00 - 18:30"),
                            f"Trạm {place.get('name')} phải đang mở cửa trong khung giờ 14:00 - 18:30")

        # 2. Khung giờ nửa đêm cho mục đích 'di_choi' (bảo tàng, di tích đóng cửa lúc 17h-18h):
        # Hệ thống phải từ chối sinh lịch trình và trả về lỗi ALL_PLACES_CLOSED (Business Rule 3)
        payload_midnight = {
            "start_location": "Chợ Bến Thành, Quận 1",
            "free_time": "02:00 - 04:00",
            "purpose": "di_choi",
            "ai_model": "rule_based"
        }
        res_mid = self.client.post("/api/ai-itinerary", json=payload_midnight).json()
        self.assertFalse(res_mid.get("feasible", True), "Khung giờ 02:00 - 04:00 không có đủ điểm tham quan mở cửa")
        self.assertEqual(res_mid.get("error_code"), "ALL_PLACES_CLOSED")
        self.assertIn("đóng cửa", res_mid.get("message", "").lower())
        self.assertIsNotNone(res_mid.get("recommended_time"), "Phải có đề xuất khung giờ thay thế")

    def test_rtm_br02_04_quick_recommend_excludes_closed_places(self):
        """[TEST-BR02-04] Tab 1 Khám phá nhanh: Quán đóng cửa bị loại bỏ 100% khi lọc theo giờ người dùng."""
        # Yêu cầu gợi ý tại thời điểm 03:00 sáng
        payload = {
            "category": "an_uong",
            "context": "ban_be",
            "price_level": "above_250k",
            "client_time": "03:00"
        }
        res = self.client.post("/api/quick-recommend", json=payload).json()
        places = res if isinstance(res, list) else res.get("places", [])
        self.assertGreater(len(places), 0, "Phải gợi ý được quán ăn đêm/24h (như Haidilao mở đến 04:00)")
        for p in places:
            # Tất cả quán trả về phải đang mở cửa tại 03:00
            self.assertTrue(p.get("is_currently_open"),
                            f"Quán {p.get('name')} đóng cửa không được gợi ý tại mốc 03:00")
            # Dim Tu Tac đóng cửa lúc 22:00 tuyệt đối không được xuất hiện
            self.assertNotIn("Dim Tu Tac", p.get("name", ""), "Quán đóng cửa lúc 22:00 không được xuất hiện lúc 03:00")

    def test_rtm_fr05_04_quick_recommend_custom_budget_too_low_redirects_to_free(self):
        """[TEST-FR05-04] Ngân sách tự nhập quá thấp (< 20.000đ) cho ẩm thực: Tự động chuyển hướng điểm 0đ, không ra quán đắt tiền."""
        payload = {
            "category": "an_uong",
            "context": "ban_be",
            "price_level": "custom",
            "custom_budget": 100,
            "offset": 0
        }
        res = self.client.post("/api/quick-recommend", json=payload).json()
        places = res if isinstance(res, list) else res.get("places", [])
        self.assertGreater(len(places), 0, "Phải gợi ý được điểm tham quan 0đ thay thế")
        for p in places:
            # Tuyệt đối không được gợi ý quán ăn đắt tiền
            self.assertEqual(p.get("min_price", 0), 0)
            self.assertEqual(p.get("max_price", 0), 0)
            self.assertIn("không đủ", p.get("free_fallback_notice", "").lower())

    # ==========================================================================
    # NHÓM 8: G6-FR06 - CHỨC NĂNG XÁO TRỘN / ĐỔI PHƯƠNG ÁN KHÁC (Ít nhất 2 phương án)
    # ==========================================================================

    def test_rtm_fr06_01_shuffle_generates_distinct_itinerary(self):
        """[TEST-FR06-01] Xáo trộn (shuffle_seed=0 vs 1) sinh ra ít nhất 2 lịch trình KHÁC BIỆT từ cùng 1 input."""
        payload_base = {
            "start_location": "Chợ Bến Thành, Quận 1",
            "free_time": "14:00 - 18:30",
            "companion": "ban_be",
            "purpose": "ca_hai",
            "ai_model": "rule_based"
        }

        # Lần 1: seed = 0
        p1 = dict(payload_base, shuffle_seed=0)
        res1 = self.client.post("/api/ai-itinerary", json=p1).json()
        stops1 = [s["place_id"] for s in res1.get("steps", [])]

        # Lần 2: seed = 1 (Xáo trộn)
        p2 = dict(payload_base, shuffle_seed=1)
        res2 = self.client.post("/api/ai-itinerary", json=p2).json()
        stops2 = [s["place_id"] for s in res2.get("steps", [])]

        self.assertNotEqual(stops1, stops2, f"Xáo trộn phải tạo ra phương án khác biệt: {stops1} vs {stops2}")

    def test_rtm_fr06_02_shuffle_respects_constraints(self):
        """[TEST-FR06-02] Phương án xáo trộn mới vẫn tôn trọng đầy đủ các ràng buộc ngân sách & thời gian."""
        payload = {
            "start_location": "Chợ Bến Thành, Quận 1",
            "free_time": "14:00 - 18:30",
            "companion": "ban_be",
            "purpose": "ca_hai",
            "shuffle_seed": 2,
            "budget_level": "100k_250k",
            "target_budget": 250000,
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload).json()
        self.assertTrue(res.get("feasible"))
        kpi = res.get("kpi", {})
        self.assertTrue(kpi.get("is_within_time"))
        self.assertEqual(len(res.get("steps", [])), 3)

    # ==========================================================================
    # NHÓM 9: G6-FR09 - IMPORT CSV HÀNG LOẠT, PHÁT HIỆN LỖI & GHI LOG KIỂM TOÁN
    # ==========================================================================

    def test_rtm_fr09_01_import_csv_detects_missing_required_fields(self):
        """[TEST-FR09-01] Import CSV phát hiện dòng bị thiếu trường bắt buộc (name/category/address)."""
        import uuid
        test_uid = uuid.uuid4().hex[:6]
        valid_name = f"Quán CSV Chuẩn {test_uid}"
        bad_csv = f"""name,category,address,district,lat,lon
{valid_name},an_uong,123 Nguyễn Trãi,Quận 5,10.75,106.66
,an_uong,456 An Dương Vương,Quận 5,10.76,106.67
Quán Thiếu Loại,,789 Trần Hưng Đạo,Quận 5,10.755,106.665
"""
        res = self.client.post("/api/admin/import-csv", json={"csv_content": bad_csv, "filename": "test_missing.csv"})
        data = res.json()
        self.assertEqual(data.get("imported_count"), 1)
        self.assertEqual(data.get("error_count"), 2)
        errors = data.get("errors", [])
        fields_with_errors = [e["field"] for e in errors]
        self.assertIn("name", fields_with_errors)
        self.assertIn("category", fields_with_errors)

        # Dọn dẹp bản ghi test vừa nạp
        conn = db.get_connection()
        conn.cursor().execute("DELETE FROM places WHERE name = ?", (valid_name,))
        conn.commit()
        conn.close()

    def test_rtm_fr09_02_import_csv_detects_invalid_numeric_types(self):
        """[TEST-FR09-02] Import CSV phát hiện dòng sai kiểu dữ liệu số (vĩ độ/kinh độ/giá)."""
        bad_csv = """name,category,address,district,lat,lon,min_price
Quán Sai Tọa Độ,an_uong,111 Hải Thượng Lãn Ông,Quận 5,abc_not_float,106.65,30000
Quán Sai Mức Giá,di_choi,222 Lương Nhữ Học,Quận 5,10.75,106.66,khong_phai_so
"""
