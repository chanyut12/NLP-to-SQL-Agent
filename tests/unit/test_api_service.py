"""API surface tests for the microservice: auth gate, health, deprecated /connect.

These avoid the NLP engine entirely — the API-key check runs as a router
dependency before any handler, and health / the /connect shim touch neither the
engine nor the datasource.
"""

import os
import sys

# Must be set before core.config / api.main are imported.
os.environ["API_KEY"] = "test-secret"
os.environ.pop("DATABASE_URL", None)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import unittest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestHealth(unittest.TestCase):
    def test_health_needs_no_key(self):
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")
        self.assertFalse(r.json()["datasource"])  # DATABASE_URL unset


class TestApiKeyGate(unittest.TestCase):
    def test_query_without_key_is_401(self):
        r = client.post("/api/query", json={"question": "x"})
        self.assertEqual(r.status_code, 401)

    def test_query_with_wrong_key_is_401(self):
        r = client.post("/api/query", json={"question": "x"},
                        headers={"X-API-Key": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_schema_without_key_is_401(self):
        r = client.get("/api/schema")
        self.assertEqual(r.status_code, 401)


class TestConnectRemoved(unittest.TestCase):
    def test_connect_endpoint_is_gone(self):
        r = client.post("/api/connect", json={},
                        headers={"X-API-Key": "test-secret"})
        self.assertIn(r.status_code, (404, 405))


class TestAdminRefreshSchema(unittest.TestCase):
    def test_refresh_schema_needs_key(self):
        self.assertEqual(client.post("/api/admin/refresh-schema").status_code, 401)


class TestSchemaEndpoint(unittest.TestCase):
    def test_schema_needs_key(self):
        self.assertEqual(client.get("/api/schema").status_code, 401)

    def test_schema_503_without_datasource(self):
        # DATABASE_URL is unset for this test module
        r = client.get("/api/schema", headers={"X-API-Key": "test-secret"})
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":
    unittest.main()
