# -*- coding: utf-8 -*-
"""
test_routing.py - Unit test suite for spatial routing and Nearest Neighbor TSP
"""
import unittest
from backend.main import calculate_haversine_distance, optimize_route_nearest_neighbor, estimate_dwell_time

class TestRouting(unittest.TestCase):
    def test_haversine_accuracy(self):
        # Chùa Bà Thiên Hậu to Hội Quán Nghĩa An ~ 0.15 km
        d = calculate_haversine_distance(10.75338, 106.65997, 10.75389, 106.66120)
        self.assertTrue(0.1 <= d <= 0.3, "Distance calculation between adjacent temples is inaccurate")

    def test_nearest_neighbor_ordering(self):
        start = (10.7500, 106.6500)
        places = [
            {"id": 1, "name": "Far Place", "lat": 10.7900, "lon": 106.7000},
            {"id": 2, "name": "Near Place", "lat": 10.7510, "lon": 106.6510},
            {"id": 3, "name": "Medium Place", "lat": 10.7600, "lon": 106.6600}
        ]
        route = optimize_route_nearest_neighbor(start, places, max_stops=3)
        self.assertEqual(len(route), 3)
        self.assertEqual(route[0]["id"], 2)
        self.assertEqual(route[1]["id"], 3)
        self.assertEqual(route[2]["id"], 1)

    def test_variable_stops_2_and_4(self):
        start = (10.7500, 106.6500)
        places = [
            {"id": 1, "name": "Place 1", "lat": 10.7510, "lon": 106.6510},
            {"id": 2, "name": "Place 2", "lat": 10.7520, "lon": 106.6520},
            {"id": 3, "name": "Place 3", "lat": 10.7530, "lon": 106.6530},
            {"id": 4, "name": "Place 4", "lat": 10.7540, "lon": 106.6540}
        ]
        route_2 = optimize_route_nearest_neighbor(start, places, max_stops=2)
        self.assertEqual(len(route_2), 2)
        route_4 = optimize_route_nearest_neighbor(start, places, max_stops=4)
        self.assertEqual(len(route_4), 4)

    def test_estimate_dwell_time(self):
        self.assertEqual(estimate_dwell_time({"category": "di_choi", "name": "Bảo tàng"}), 40)
        self.assertEqual(estimate_dwell_time({"category": "an_uong", "name": "Cà phê Cheo Leo"}), 30)
        self.assertEqual(estimate_dwell_time({"category": "an_uong", "name": "Quán Ốc Đào"}), 60)
        self.assertEqual(estimate_dwell_time({"category": "an_uong", "name": "Cơm tấm Ba Ghiền"}), 45)

if __name__ == "__main__":
    unittest.main()

<!-- ref: test(routing): write test_tsp_3_stops_optimal_sequence -->
