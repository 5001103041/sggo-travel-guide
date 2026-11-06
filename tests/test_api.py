# -*- coding: utf-8 -*-
"""
test_api.py - Integration test suite for REST API endpoints
"""
import unittest
from fastapi.testclient import TestClient
from backend.main import app

class TestAPIEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_check(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_get_places(self):
        response = self.client.get("/api/places")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_get_place_detail_404(self):
        response = self.client.get("/api/places/999999")
        self.assertEqual(response.status_code, 404)

if __name__ == "__main__":
    unittest.main()

<!-- ref: test(api): write test_get_all_places and category filter assertion -->
