"""Deployment-mode tests: APP_MODE=demo vs APP_MODE=service vs auto.

The app factory is called with patched settings so these tests do not depend on
the developer's .env (which may point at the STS datasource or set an API key).
"""

import os
import sys
import unittest
from contextlib import contextmanager
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from fastapi.testclient import TestClient


@contextmanager
def app_client(mode: str, api_key: str):
    """Build an app under a settings patch and keep the patch active for requests.

    Imports are intentionally inside this helper: importing api.main (or
    core.config) during collection would load .env before test_api_service has a
    chance to set its own environment, making these tests order-dependent.
    """
    from api.main import create_app
    from core.config import settings

    with (
        patch.object(settings, "APP_MODE", mode),
        patch.object(settings, "API_KEY", api_key),
        patch.object(settings, "DATABASE_URL", ""),
        patch.object(settings, "CORS_ORIGINS", "*"),
    ):
        yield TestClient(create_app())


def validate(mode: str, api_key: str) -> str:
    from core.config import validate_app_mode

    return validate_app_mode(mode, api_key)


class TestValidateAppMode(unittest.TestCase):
    def test_auto_is_valid_with_or_without_key(self):
        self.assertEqual(validate("auto", ""), "auto")
        self.assertEqual(validate("auto", "secret"), "auto")

    def test_demo_requires_no_api_key(self):
        self.assertEqual(validate("demo", ""), "demo")
        with self.assertRaises(ValueError):
            validate("demo", "secret")

    def test_service_requires_api_key(self):
        self.assertEqual(validate("service", "secret"), "service")
        with self.assertRaises(ValueError):
            validate("service", "")

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            validate("staging", "secret")


class TestDemoMode(unittest.TestCase):
    def test_demo_serves_ui_without_a_key(self):
        with app_client("demo", "") as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Thai NLP", response.text)

    def test_demo_api_is_unauthenticated(self):
        with app_client("demo", "") as client:
            # /api/history needs no engine, so this tests only the auth gate.
            self.assertEqual(client.get("/api/history?limit=1").status_code, 200)

    def test_demo_docs_are_available(self):
        with app_client("demo", "") as client:
            self.assertEqual(client.get("/docs").status_code, 200)

    def test_demo_health_needs_no_key(self):
        with app_client("demo", "") as client:
            self.assertEqual(client.get("/api/health").status_code, 200)


class TestServiceMode(unittest.TestCase):
    def test_service_does_not_serve_ui(self):
        with app_client("service", "test-secret") as client:
            self.assertEqual(client.get("/").status_code, 404)

    def test_service_rejects_requests_without_key(self):
        with app_client("service", "test-secret") as client:
            self.assertEqual(client.post("/api/query", json={}).status_code, 401)

    def test_service_accepts_a_valid_key(self):
        with app_client("service", "test-secret") as client:
            response = client.get(
                "/api/history?limit=1",
                headers={"X-API-Key": "test-secret"},
            )
            self.assertEqual(response.status_code, 200)

    def test_service_hides_docs(self):
        with app_client("service", "test-secret") as client:
            self.assertEqual(client.get("/docs").status_code, 404)


class TestAutoMode(unittest.TestCase):
    """APP_MODE unset must keep the pre-existing UI/API_KEY behaviour."""

    def test_auto_without_key_serves_ui_and_no_auth(self):
        with app_client("auto", "") as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/api/history?limit=1").status_code, 200)

    def test_auto_with_key_hides_ui_and_requires_auth(self):
        with app_client("auto", "test-secret") as client:
            self.assertEqual(client.get("/").status_code, 404)
            self.assertEqual(client.post("/api/query", json={}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
