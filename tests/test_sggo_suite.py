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
        res = self.client.post("/api/admin/import-csv", json={"csv_content": bad_csv, "filename": "test_types.csv"})
        data = res.json()
        self.assertEqual(data.get("imported_count"), 0)
        self.assertEqual(data.get("error_count"), 2)
        fields = [e["field"] for e in data.get("errors", [])]
        self.assertIn("lat", fields)
        self.assertIn("min_price", fields)

    def test_rtm_fr09_03_import_csv_detects_duplicates_and_logs_audit(self):
        """[TEST-FR09-03] Import CSV phát hiện trùng lặp địa điểm và ghi log kiểm toán vào bảng import_logs."""
        # Lấy tên của 1 quán đã có sẵn trong DB
        existing_places = db.get_all_places()
        self.assertGreater(len(existing_places), 0)
        existing_name = existing_places[0]["name"]

        dup_csv = f"""name,category,address,district,lat,lon
{existing_name},an_uong,123 Trùng Lặp,Quận 5,10.75,106.66
"""
        res = self.client.post("/api/admin/import-csv", json={"csv_content": dup_csv, "filename": "test_duplicate.csv"})
        data = res.json()
        self.assertEqual(data.get("error_count"), 1)
        self.assertEqual(data.get("errors")[0]["field"], "name")
        self.assertIn("đã tồn tại", data.get("errors")[0]["reason"])

        # Kiểm tra bảng import_logs đã được ghi nhận vào CSDL
        logs_res = self.client.get("/api/admin/import-logs?limit=5")
        self.assertEqual(logs_res.status_code, 200)
        logs = logs_res.json()
        self.assertGreater(len(logs), 0)
        self.assertEqual(logs[0]["filename"], "test_duplicate.csv")
        self.assertEqual(logs[0]["error_count"], 1)



    def test_rtm_fr08_01_admin_tag_management_crud(self):
        """[TEST-FR08-01] Admin quản lý danh mục tag/tiêu chí: xem, thêm, bật/tắt và xóa tag (G6-FR08)."""
        # 1. Xem danh sách tags
        get_res = self.client.get("/api/admin/tags")
        self.assertEqual(get_res.status_code, 200)
        tags = get_res.json().get("tags", [])
        self.assertGreaterEqual(len(tags), 4)

        # 2. Thêm tag mới
        new_tag = {"tag_key": "test_tag_moi", "name": "Tag Thử Nghiệm", "tier_type": "feature"}
        post_res = self.client.post("/api/admin/tags", json=new_tag)
        self.assertEqual(post_res.status_code, 200)
        tag_id = post_res.json().get("id")
        self.assertIsNotNone(tag_id)

        # 3. Bật/tắt trạng thái tag
        toggle_res = self.client.post(f"/api/admin/tags/{tag_id}/toggle", json={"is_active": 0})
        self.assertEqual(toggle_res.status_code, 200)
        self.assertEqual(toggle_res.json().get("is_active"), 0)

        # 4. Xóa tag vừa tạo
        del_res = self.client.delete(f"/api/admin/tags/{tag_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(del_res.json().get("status"), "success")

    def test_rtm_br02_03_closed_place_excluded_from_itinerary(self):
        """[TEST-BR02-03] Business Rule 2: Địa điểm đóng cửa không được đưa vào lịch trình."""
        # Yêu cầu lịch trình vào lúc nửa đêm (00:00 - 02:00)
        # Các bảo tàng/di tích chỉ mở cửa 07:30 - 17:00 tuyệt đối không được xuất hiện
        payload = {
            "start_location": "Chợ Bến Thành, Quận 1",
            "free_time": "00:00 - 02:00",
            "companion": "ban_be",
            "purpose": "di_choi",
            "budget": "tuy_duyen",
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        if data.get("feasible") is not False:
            steps = data.get("steps", [])
            for s in steps:
                hours = s.get("open_hours", "")
                # Không được là điểm đóng cửa lúc 17:00
                self.assertNotIn("07:30 - 17:00", hours)

    def test_rtm_fr10_01_itinerary_stop_has_rule_explanation(self):
        """[TEST-FR10-01] G6-FR10 SHOULD: Từng trạm dừng có giải thích rule/tiêu chí gợi ý rõ ràng."""
        payload = {
            "start_location": "280 An Dương Vương, TP.HCM",
            "free_time": "14:00 - 18:30",
            "companion": "nhom_ban",
            "purpose": "an_uong",
            "budget": "100k_250k",
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        if data.get("feasible") is not False:
            steps = data.get("steps", [])
            self.assertGreaterEqual(len(steps), 3)
            for s in steps:
                self.assertIn("rule_explanation", s)
                self.assertTrue(len(s["rule_explanation"]) > 5)

    def test_rtm_fr09_04_excel_sample_download(self):
        """[TEST-FR09-04] G6-FR09 SHOULD: Tải file Excel mẫu (.xlsx) hợp lệ với định dạng binary chuẩn."""
        res = self.client.get("/api/admin/sample-excel")
        self.assertEqual(res.status_code, 200)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", res.headers.get("content-type", ""))
        self.assertGreater(len(res.content), 2000)

    def test_rtm_fr09_05_excel_import_valid_and_invalid_data(self):
        """[TEST-FR09-05] G6-FR09 SHOULD: Import hàng loạt từ file Excel (.xlsx), phát hiện dòng lỗi và nạp dòng đúng."""
        import openpyxl
        import io
        import base64
        import uuid

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["name", "category", "address", "district", "lat", "lon", "min_price", "max_price", "rating"])
        
        valid_name = f"Quán Excel Test {uuid.uuid4().hex[:6]}"
        ws.append([valid_name, "an_uong", "888 An Dương Vương, Quận 5", "Quận 5", 10.755, 106.665, 45000, 70000, 4.8])
        # Dòng lỗi: thiếu tên quán
        ws.append(["", "an_uong", "123 Địa Chỉ, Quận 5", "Quận 5", 10.75, 106.66, 30000, 50000, 4.5])
        
        buf = io.BytesIO()
        wb.save(buf)
        b64_content = base64.b64encode(buf.getvalue()).decode("ascii")

        res = self.client.post("/api/admin/import-excel", json={
            "file_base64": b64_content,
            "filename": "test_import_excel.xlsx"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("imported_count"), 1)
        self.assertEqual(data.get("error_count"), 1)
        self.assertEqual(data.get("errors")[0]["field"], "name")

        # Kiểm tra bảng import_logs đã ghi nhận file xlsx
        logs_res = self.client.get("/api/admin/import-logs?limit=5")
        self.assertEqual(logs_res.status_code, 200)
        logs = logs_res.json()
        self.assertEqual(logs[0]["filename"], "test_import_excel.xlsx")
        self.assertEqual(logs[0]["success_count"], 1)

        # Dọn dẹp quán test sau khi kiểm thử
        conn = db.get_connection()
        conn.cursor().execute("DELETE FROM places WHERE name = ?", (valid_name,))
        conn.commit()
        conn.close()
        db.sync_db_to_json()

    def test_rtm_fr05_03_strict_budget_adherence(self):
        """[TEST-FR05-03] G6-FR05 MUST: Lịch trình tối ưu ngân sách cam kết nằm trong ngân sách dự kiến của người dùng."""
        payload = {
            "start_location": "Chợ Bến Thành, Quận 1",
            "free_time": "14:00 - 18:30",
            "companion": "nhom_ban",
            "purpose": "an_uong",
            "budget": "100k_250k",
            "target_budget": 250000,
            "ai_model": "rule_based"
        }
        res = self.client.post("/api/ai-itinerary", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        if data.get("feasible") is not False:
            kpi = data.get("kpi", {})
            self.assertTrue(kpi.get("is_within_budget"), "Lịch trình phải đảm bảo nằm trong ngân sách dự kiến")
            self.assertLessEqual(kpi.get("total_min_cost", 0), 250000)

    def test_rtm_fr01_05_create_place_prevents_duplicate(self):
        """[TEST-FR01-05] Backend phát hiện và ngăn chặn thêm địa điểm trùng lặp (Tên + Địa chỉ)."""
        places = db.get_all_places()
        self.assertGreater(len(places), 0)
        p = places[0]
        dup_payload = {
            "name": p["name"],
            "address": p["address"],
            "category": "an_uong",
            "district": p.get("district", "Quận 1"),
            "lat": 10.7725,
            "lon": 106.6980,
            "open_time": "08:00",
            "close_time": "22:00",
            "min_price": 30000,
            "max_price": 70000
        }
        res = self.client.post("/api/admin/places", json=dup_payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("đã tồn tại trong CSDL", res.json().get("detail", ""))

    def test_rtm_fr01_06_extract_gmaps_clean_data(self):
        """[TEST-FR01-06] Endpoint extract-gmaps từ chối tên quán, chỉ nhận link Google Maps và không sinh dữ liệu giá/giờ/sao ảo."""
        # 1. Từ chối nhập tên quán
        res_text = self.client.post("/api/admin/extract-gmaps", json={"url_or_query": "Địa Điểm Kiểm Tra Tính Minh Bạch"})
        self.assertEqual(res_text.status_code, 400)
        self.assertIn("chỉ hỗ trợ bóc tách từ đường link Google Maps", res_text.json().get("detail", ""))

        # 2. Bóc tách link Google Maps không sinh dữ liệu giá, giờ, rating ảo
        valid_map_url = "https://www.google.com/maps/place/Quan+An+Thu+Nghiem/@10.7725,106.6980,17z"
        res = self.client.post("/api/admin/extract-gmaps", json={"url_or_query": valid_map_url})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("place", data)
        p = data["place"]
        self.assertEqual(p["name"], "Quan An Thu Nghiem")
        self.assertEqual(p["lat"], 10.7725)
        self.assertEqual(p["lon"], 106.6980)
        # Giá, giờ hoạt động và rating không được gán số ảo (để trống cho admin tự nhập)
        self.assertIsNone(p["min_price"])
        self.assertIsNone(p["max_price"])
        self.assertIsNone(p["rating"])
        self.assertIsNone(p["reviews_count"])
        self.assertEqual(p["open_time"], "")
        self.assertEqual(p["close_time"], "")

    def test_rtm_fr01_07_prevent_duplicate_street_address_with_different_name(self):
        """[TEST-FR01-07] Chống trùng lặp địa chỉ nhà phố: Ngăn chặn thêm địa điểm mới nếu trùng địa chỉ mặt phố dù tên hoàn toàn khác."""
        places = db.get_all_places()
        self.assertGreater(len(places), 0)
        # Tìm quán mặt phố không phải TTTM
        p = None
        for item in places:
            if not db.is_commercial_complex(item["address"], item["name"]):
                p = item
                break
        self.assertIsNotNone(p)

        # Thử thêm quán với tên hoàn toàn khác nhưng trùng đúng địa chỉ nhà phố của p
        fake_payload = {
            "name": "Quán Trà Sữa Tự Phát Hoàn Toàn Mới 999",
            "category": "an_uong",
            "address": p["address"],
            "district": p.get("district", "Quận 1"),
            "lat": 10.7735,
            "lon": 106.6980,
            "open_time": "08:00",
            "close_time": "22:00",
            "min_price": 25000,
            "max_price": 50000
        }
        res = self.client.post("/api/admin/places", json=fake_payload)
        self.assertEqual(res.status_code, 400)
        detail = res.json().get("detail", "")
        self.assertIn("đã tồn tại trong CSDL", detail)
        self.assertIn("Trùng hoàn toàn địa chỉ", detail)

    def test_rtm_fr01_08_strict_data_constraints_validation(self):
        """[TEST-FR01-08] Ràng buộc dữ liệu chặt chẽ: kiểm tra giá tối đa < tối thiểu, tọa độ ngoài TP.HCM, số sao ngoài 0-5."""
        # 1. max_price < min_price
        bad_price = {
            "name": "Quán Kiểm Tra Ràng Buộc Giá",
            "category": "an_uong",
            "address": "999 Đường Kiểm Tra Ràng Buộc, Quận 5",
            "district": "Quận 5",
            "lat": 10.7550,
            "lon": 106.6650,
            "min_price": 80000,
            "max_price": 30000 # nhỏ hơn min_price
        }
        res_price = self.client.post("/api/admin/places", json=bad_price)
        self.assertEqual(res_price.status_code, 400)
        self.assertIn("Mức giá tối đa không được nhỏ hơn mức giá tối thiểu", res_price.json().get("detail", ""))

        # 2. Tọa độ ngoài TP.HCM (ví dụ tọa độ Hà Nội lat=21.0, lon=105.8)
        bad_gps = {
            "name": "Quán Kiểm Tra Ràng Buộc GPS",
            "category": "an_uong",
            "address": "999 Đường Kiểm Tra Ràng Buộc, Quận 5",
            "district": "Quận 5",
            "lat": 21.0285, # Hà Nội
            "lon": 105.8542,
            "min_price": 30000,
            "max_price": 50000
        }
        res_gps = self.client.post("/api/admin/places", json=bad_gps)
        self.assertEqual(res_gps.status_code, 400)
        self.assertIn("phạm vi TP.HCM", res_gps.json().get("detail", ""))

        # 3. Đánh giá sao không hợp lệ (ví dụ: 6.5 sao)
        bad_star = {
            "name": "Quán Kiểm Tra Ràng Buộc Sao",
            "category": "an_uong",
            "address": "999 Đường Kiểm Tra Ràng Buộc, Quận 5",
            "district": "Quận 5",
            "lat": 10.7550,
            "lon": 106.6650,
            "min_price": 30000,
            "max_price": 50000,
            "rating": 6.5 # vượt quá 5.0
        }
        res_star = self.client.post("/api/admin/places", json=bad_star)
        self.assertEqual(res_star.status_code, 400)
        self.assertIn("0.0 đến 5.0", res_star.json().get("detail", ""))

    def test_rtm_fr01_09_prevent_duplicate_mall_floor_address(self):
        """[TEST-FR01-09] Chống trùng lặp địa chỉ trong TTTM: Nhập địa chỉ cụ thể của Haidilao ở Vạn Hạnh Mall với tên khác vẫn bị chặn."""
        mall_payload = {
            "name": "Quán Trà Sữa Thử Nghiệm Tầng 4",
            "category": "an_uong",
            "address": "Tầng4Vạn Hạnh Mall, 11 Sư Vạn Hạnh, Hòa Hưng, Hồ Chí Minh, Việt Nam",
            "district": "Quận 10",
            "lat": 10.7705,
            "lon": 106.6696,
            "open_time": "09:00",
            "close_time": "22:00",
            "min_price": 40000,
            "max_price": 90000
        }
        res = self.client.post("/api/admin/places", json=mall_payload)
        self.assertEqual(res.status_code, 400)
        detail = res.json().get("detail", "")
        self.assertIn("đã tồn tại trong CSDL", detail)
        self.assertIn("Haidilao Hotpot Vạn Hạnh Mall", detail)

    def test_rtm_sec_rbac_admin_forbidden_for_non_admin(self):
        """[TEST-SEC-01] Bảo mật RBAC: Khách và User thông thường không được gọi API quản trị Admin (403 Forbidden)."""
        non_admin_client = TestClient(app)
        
        # 1. POST /api/admin/places
        res1 = non_admin_client.post("/api/admin/places", json={"name": "Fake Place", "category": "an_uong", "address": "123 Đường Test, Quận 5"})
        self.assertEqual(res1.status_code, 403)
        self.assertIn("Yêu cầu quyền Quản trị viên", res1.json().get("detail", ""))

        # 2. GET /api/admin/users
        res2 = non_admin_client.get("/api/admin/users")
        self.assertEqual(res2.status_code, 403)

        # 3. GET /api/admin/stats
        res3 = non_admin_client.get("/api/admin/stats")
        self.assertEqual(res3.status_code, 403)

        # 4. DELETE /api/admin/places/1
        res4 = non_admin_client.delete("/api/admin/places/1")
        self.assertEqual(res4.status_code, 403)

    def test_rtm_sec_password_hashing_and_auto_migration(self):
        """[TEST-SEC-02] An toàn mật khẩu: Mật khẩu được mã hóa SHA-256 kèm salt, tự động nâng cấp mật khẩu cũ."""
        pwd = "SecretPassword123!"
        hashed = db.hash_password(pwd)
        self.assertTrue(hashed.startswith("sha256:"))
        self.assertEqual(len(hashed.split(":")), 3)

        # Xác thực thành công với đúng mật khẩu
        self.assertTrue(db.verify_password(hashed, pwd))
        # Thất bại với mật khẩu sai
        self.assertFalse(db.verify_password(hashed, "wrongPassword"))

        # Đăng ký tài khoản mới được lưu dưới dạng băm
        new_u = db.register_user("test_hash_user", "mySafePass123", "Test Hash")
        self.assertIsNotNone(new_u)
        conn = db.get_connection()
        row = conn.execute("SELECT password FROM users WHERE id = ?", (new_u["id"],)).fetchone()
        conn.close()
        self.assertTrue(row[0].startswith("sha256:"))
        db.delete_user(new_u["id"])

    def test_rtm_sec_register_validation(self):
        """[TEST-SEC-03] Kiểm tra ràng buộc đăng ký tài khoản (Username, Password, Full Name)."""
        # 1. Username quá ngắn (< 3 ký tự)
        res1 = self.client.post("/api/auth/register", json={"username": "ab", "password": "password123", "full_name": "Tên Hợp Lệ"})
        self.assertEqual(res1.status_code, 400)
        self.assertIn("từ 3 đến 30 ký tự", res1.json().get("detail", ""))

        # 2. Username chứa khoảng trắng hoặc ký tự đặc biệt
        res2 = self.client.post("/api/auth/register", json={"username": "user test!", "password": "password123", "full_name": "Tên Hợp Lệ"})
        self.assertEqual(res2.status_code, 400)

        # 3. Password quá ngắn (< 6 ký tự)
        res3 = self.client.post("/api/auth/register", json={"username": "valid_user_1", "password": "123", "full_name": "Tên Hợp Lệ"})
        self.assertEqual(res3.status_code, 400)
        self.assertIn("tối thiểu 6 ký tự", res3.json().get("detail", ""))

        # 4. Full name quá ngắn (< 2 ký tự)
        res4 = self.client.post("/api/auth/register", json={"username": "valid_user_2", "password": "password123", "full_name": "A"})
        self.assertEqual(res4.status_code, 400)
        self.assertIn("tối thiểu 2 ký tự", res4.json().get("detail", ""))

    def test_rtm_ddl_foreign_keys_and_cascade(self):
        """[TEST-DDL-01] Ràng buộc khóa ngoại PRAGMA foreign_keys = ON & Cơ chế xóa lan truyền ON DELETE CASCADE trên place_tags."""
        # Tạo địa điểm test
        p = db.add_place({
            "name": "[TEST_CASCADE] Quán Test Xóa Lan Truyền",
            "category": "an_uong",
            "address": "777 Đ. Hải Thượng Lãn Ông, Phường 10, Quận 5",
            "district": "Quận 5",
            "lat": 10.7510,
            "lon": 106.6610,
            "min_price": 20000,
            "max_price": 50000
        })
        p_id = p["id"]

        # Gán tag cho địa điểm test
        conn = db.get_connection()
        conn.execute("INSERT OR IGNORE INTO place_tags (place_id, tag_id) VALUES (?, 1)", (p_id,))
        conn.commit()

        # Kiểm tra tồn tại trong place_tags
        count_before = conn.execute("SELECT COUNT(*) FROM place_tags WHERE place_id = ?", (p_id,)).fetchone()[0]
        self.assertEqual(count_before, 1)

        # Xóa địa điểm
        db.delete_place(p_id)

        # Kiểm tra tự động xóa lan truyền khỏi place_tags
        count_after = conn.execute("SELECT COUNT(*) FROM place_tags WHERE place_id = ?", (p_id,)).fetchone()[0]
        conn.close()
        self.assertEqual(count_after, 0)

    def test_rtm_admin_stats_and_accuracy(self):
        """[TEST-STAT-01] Kiểm tra độ chính xác của API số liệu thống kê Admin Dashboard (total_places, verified_places, total_users)."""
        stat = self.client.get("/api/admin/stats").json()
        self.assertIn("total_places", stat)
        self.assertIn("verified_places", stat)
        self.assertIn("total_users", stat)
        self.assertGreaterEqual(stat["total_places"], 40)
        self.assertGreaterEqual(stat["total_users"], 1)

    def test_rtm_address_abbreviation_expansion_duplicate_detection(self):
        """[TEST-BR-04] Mở rộng từ viết tắt địa chỉ tiếng Việt (đ., p., q., tp., tttm) để chống trùng lặp triệt để."""
        text = "85 đ. Trần Bình Trọng, p.1, q.5, tphcm"
        expanded = db.expand_address_abbreviations(text)
        self.assertIn("đường", expanded.lower())
        self.assertIn("phường", expanded.lower())
        self.assertIn("quận", expanded.lower())
        self.assertIn("thành phố hồ chí minh", expanded.lower())

        # Thử thêm địa chỉ viết tắt của địa điểm có sẵn (135 Nam Kỳ Khởi Nghĩa, Phường Bến Thành, Quận 1)
        dup_payload = {
            "name": "Quán Trà Sữa Mới Toanh",
            "category": "an_uong",
            "address": "135 đ. Nam Kỳ Khởi Nghĩa, p. Bến Thành, q.1, tphcm",
            "district": "Quận 1",
            "lat": 10.7770,
            "lon": 106.6950,
            "min_price": 25000,
            "max_price": 50000
        }
        res = self.client.post("/api/admin/places", json=dup_payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("đã tồn tại trong CSDL", res.json().get("detail", ""))
        self.assertIn("Dinh Độc Lập", res.json().get("detail", ""))

    def test_rtm_district_and_time_format_validation(self):
        """[TEST-BR-05] Ràng buộc 22 Quận/Huyện hợp lệ của TP.HCM, định dạng giờ chuẩn HH:MM và trần giá tiền."""
        # 1. Quận ngoài TP.HCM
        bad_dist = {
            "name": "Quán Quận Lạ",
            "category": "an_uong",
            "address": "123 Đường Test, Hà Nội",
            "district": "Ba Đình",
            "lat": 10.7550,
            "lon": 106.6650,
            "min_price": 30000,
            "max_price": 50000
        }
        res1 = self.client.post("/api/admin/places", json=bad_dist)
        self.assertEqual(res1.status_code, 400)
        self.assertIn("22 quận/huyện", res1.json().get("detail", ""))

        # 2. Giờ mở cửa sai định dạng (ví dụ: '8h sáng' hoặc '25:70')
        bad_time = {
            "name": "Quán Giờ Sai",
            "category": "an_uong",
            "address": "123 Đường Test, Quận 5",
            "district": "Quận 5",
            "lat": 10.7550,
            "lon": 106.6650,
            "open_time": "25:70",
            "close_time": "22:00",
            "min_price": 30000,
            "max_price": 50000
        }
        res2 = self.client.post("/api/admin/places", json=bad_time)
        self.assertEqual(res2.status_code, 400)
        self.assertIn("định dạng chuẩn (HH:MM", res2.json().get("detail", ""))

        # 3. Giá tiền vượt trần 50,000,000 VNĐ
        bad_price = {
            "name": "Quán Giá Quá Cao",
            "category": "an_uong",
            "address": "123 Đường Test, Quận 5",
            "district": "Quận 5",
            "lat": 10.7550,
            "lon": 106.6650,
            "min_price": 60000000,
            "max_price": 100000000
        }
        res3 = self.client.post("/api/admin/places", json=bad_price)
        self.assertEqual(res3.status_code, 400)
        self.assertIn("50,000,000", res3.json().get("detail", ""))

    def test_quick_recommend_with_gps_and_distance_priority(self):
        """[TEST-FR-GPS] Kiểm tra tính năng đồng bộ GPS và ưu tiên khoảng cách ở Quick Recommend."""
        # Tọa độ kiểm tra: Nhà Thờ Đức Bà, Quận 1 (10.7798, 106.6990)
        user_lat = 10.7798
        user_lon = 106.6990

        # 1. Gọi khi có GPS nhưng chưa bật prioritize_distance
        res_no_prio = self.client.post("/api/quick-recommend", json={
            "category": "all",
            "context": "all",
            "price_level": "all",
            "user_lat": user_lat,
            "user_lon": user_lon,
            "prioritize_distance": False,
            "client_time": "10:00"
        })
        self.assertEqual(res_no_prio.status_code, 200)
        data_no_prio = res_no_prio.json()
        self.assertTrue(len(data_no_prio) > 0)
        # Kiểm tra trường distance_km được tính toán
        self.assertIn("distance_km", data_no_prio[0])
        self.assertIsInstance(data_no_prio[0]["distance_km"], (int, float))

        # 2. Gọi khi có GPS VÀ BẬT prioritize_distance = True
        res_with_prio = self.client.post("/api/quick-recommend", json={
            "category": "all",
            "context": "all",
            "price_level": "all",
            "user_lat": user_lat,
            "user_lon": user_lon,
            "prioritize_distance": True,
            "client_time": "10:00"
        })
        self.assertEqual(res_with_prio.status_code, 200)
        data_with_prio = res_with_prio.json()
        self.assertTrue(len(data_with_prio) > 0)
        # Các quán trong top 3 khi bật ưu tiên khoảng cách phải có khoảng cách gần hơn đáng kể
        avg_dist_prio = sum(p.get("distance_km", 99) for p in data_with_prio[:3]) / 3
        self.assertLessEqual(avg_dist_prio, 8.0, f"Khoảng cách trung bình top 3 phải <= 8km nhưng là {avg_dist_prio}")

if __name__ == "__main__":
    unittest.main()

