"""Demo-mode datasource switching (ADR 0013).

The connect endpoint exists only where the bundled UI is served, so these tests
build the app under patched settings and point it at throwaway SQLite files.
``GlobalStateManager`` is a module-level singleton, so every test restores the
datasource and engine it found — otherwise a later test would inherit them.
"""

import os
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from fastapi.testclient import TestClient


@contextmanager
def app_client(mode: str, api_key: str):
    """Build an app under a settings patch and keep the patch active for requests."""
    from api.main import create_app
    from api.dependencies import state_manager
    from core.config import settings

    previous_engine = state_manager.db_engine
    previous_nlp_engine = state_manager.nlp_engine
    with (
        patch.object(settings, "APP_MODE", mode),
        patch.object(settings, "API_KEY", api_key),
        patch.object(settings, "DATABASE_URL", ""),
        patch.object(settings, "CORS_ORIGINS", "*"),
        patch.object(settings, "DOMAIN_PROFILE", "demo"),
    ):
        try:
            yield TestClient(create_app())
        finally:
            state_manager.db_engine = previous_engine
            state_manager.nlp_engine = previous_nlp_engine


def make_sqlite_file(tmpdir: str, name: str, table: str) -> str:
    """An absolute SQLite file with one table, for the demo to connect to."""
    path = os.path.join(tmpdir, name)
    connection = sqlite3.connect(path)
    try:
        connection.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, label TEXT)")
        connection.execute(f"INSERT INTO {table} (label) VALUES ('x')")
        connection.commit()
    finally:
        connection.close()
    return path


def schema_table_names(client: TestClient) -> list:
    response = client.get("/api/schema")
    assert response.status_code == 200, response.text
    return sorted(table["name"] for table in response.json()["tables"])


def connect(client: TestClient, database_url: str, profile: str = None):
    payload = {"database_url": database_url}
    if profile is not None:
        payload["profile"] = profile
    return client.post("/api/demo/connect", json=payload)


class TestDemoRoutesAreMounted(unittest.TestCase):
    def test_service_mode_has_no_demo_routes(self):
        with app_client("service", "test-secret") as client:
            headers = {"X-API-Key": "test-secret"}
            self.assertEqual(client.get("/api/demo/state", headers=headers).status_code, 404)
            self.assertEqual(
                client.post(
                    "/api/demo/connect",
                    json={"database_url": "sqlite:///x.db"},
                    headers=headers,
                ).status_code,
                404,
            )

    def test_demo_state_lists_profiles_and_the_active_one(self):
        with app_client("demo", "") as client:
            response = client.get("/api/demo/state")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["profile"], "demo")
            self.assertIn("demo", body["profiles"])
            self.assertIn("sts", body["profiles"])

    def test_auto_mode_without_a_key_serves_the_demo_routes(self):
        with app_client("auto", "") as client:
            self.assertEqual(client.get("/api/demo/state").status_code, 200)


class TestDemoConnect(unittest.TestCase):
    def test_connect_switches_the_datasource_everywhere(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = make_sqlite_file(tmpdir, "other.db", "schools")
            with app_client("demo", "") as client:
                response = connect(client, f"sqlite:///{path}", profile="demo")

                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body["tables"], ["schools"])
                self.assertEqual(body["datasource"], f"sqlite:///{path}")
                self.assertEqual(body["profile"], "demo")
                # /api/schema reads the swapped manager, not a copy.
                self.assertEqual(schema_table_names(client), ["schools"])

    def test_malformed_dsn_is_rejected_and_nothing_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = make_sqlite_file(tmpdir, "keep.db", "keep_table")
            with app_client("demo", "") as client:
                self.assertEqual(connect(client, f"sqlite:///{path}").status_code, 200)

                bad = connect(client, "not a dsn")
                self.assertEqual(bad.status_code, 400)
                self.assertIn("Connection string", bad.json()["detail"])
                self.assertEqual(schema_table_names(client), ["keep_table"])

    def test_unreachable_datasource_is_rejected_and_nothing_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = make_sqlite_file(tmpdir, "keep.db", "keep_table")
            missing = os.path.join(tmpdir, "no-such-dir", "x.db")
            with app_client("demo", "") as client:
                self.assertEqual(connect(client, f"sqlite:///{path}").status_code, 200)

                failed = connect(client, f"sqlite:///{missing}")
                self.assertEqual(failed.status_code, 400)
                self.assertIn("เชื่อมต่อไม่สำเร็จ", failed.json()["detail"])
                self.assertEqual(schema_table_names(client), ["keep_table"])

    def test_unknown_profile_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = make_sqlite_file(tmpdir, "other.db", "schools")
            with app_client("demo", "") as client:
                response = connect(client, f"sqlite:///{path}", profile="no-such-profile")
                self.assertEqual(response.status_code, 400)
                self.assertIn("profile", response.json()["detail"])

    def test_profile_only_switch_keeps_the_connected_datasource(self):
        from api.dependencies import state_manager
        from core.config import settings

        with tempfile.TemporaryDirectory() as tmpdir:
            path = make_sqlite_file(tmpdir, "other.db", "schools")
            with app_client("demo", "") as client:
                self.assertEqual(connect(client, f"sqlite:///{path}").status_code, 200)
                state_manager.nlp_engine = object()

                # No database_url: the wizard switches to the profile it just
                # wrote without needing the password the state redacts.
                response = client.post("/api/demo/connect", json={"profile": "sts"})

                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body["profile"], "sts")
                self.assertEqual(body["datasource"], f"sqlite:///{path}")
                self.assertEqual(body["tables"], ["schools"])
                self.assertEqual(settings.DOMAIN_PROFILE, "sts")
                self.assertIsNone(state_manager.nlp_engine)

    def test_profile_only_switch_without_a_datasource_is_rejected(self):
        from api.dependencies import state_manager

        with app_client("demo", "") as client:
            # The singleton may carry the developer's startup Datasource; this
            # case is about a demo that never connected at all.
            state_manager.db_engine = None
            response = client.post("/api/demo/connect", json={"profile": "demo"})
            self.assertEqual(response.status_code, 400)
            self.assertIn("database_url", response.json()["detail"])

    def test_profile_switch_updates_settings_and_drops_the_engine(self):
        from api.dependencies import state_manager
        from core.config import settings

        with tempfile.TemporaryDirectory() as tmpdir:
            path = make_sqlite_file(tmpdir, "other.db", "schools")
            with app_client("demo", "") as client:
                # Pretend the demo already answered a question: the engine binds
                # the profile at construction, so it must not be reused.
                state_manager.nlp_engine = object()

                response = connect(client, f"sqlite:///{path}", profile="sts")

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["profile"], "sts")
                self.assertEqual(settings.DOMAIN_PROFILE, "sts")
                self.assertIsNone(state_manager.nlp_engine)


class TestRedaction(unittest.TestCase):
    def test_password_never_leaves_the_server(self):
        from api.demo_routes import redacted_url, safe_error

        dsn = "postgresql+psycopg2://analyst:s3cret@db.example:5432/sts"
        self.assertNotIn("s3cret", redacted_url(dsn))
        self.assertIn("analyst", redacted_url(dsn))
        self.assertNotIn(
            "s3cret", safe_error(RuntimeError(f"could not connect to {dsn}"), dsn)
        )


class TestDatasourceKey(unittest.TestCase):
    def test_same_datasource_keeps_one_key(self):
        from core.data.schema_rag import datasource_key

        self.assertEqual(
            datasource_key("sqlite:///./local_database.db"),
            datasource_key("sqlite:///./local_database.db"),
        )

    def test_another_database_gets_another_key(self):
        from core.data.schema_rag import datasource_key

        first = datasource_key("postgresql+psycopg2://u:p@host:5432/sts")
        second = datasource_key("postgresql+psycopg2://u:p@host:5432/other")
        self.assertNotEqual(first, second)

    def test_collection_name_is_namespaced_and_chroma_safe(self):
        from core.data.schema_rag import SchemaRAG, datasource_key

        key = datasource_key("sqlite:///./local_database.db")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{12}", key))
        rag = SchemaRAG(profile="demo", datasource=key)
        self.assertTrue(rag.collection_name.startswith("schema_metadata_demo_"))
        self.assertLessEqual(len(rag.collection_name), 63)


if __name__ == "__main__":
    unittest.main()
