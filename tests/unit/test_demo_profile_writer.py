"""Demo-mode profile authoring: the wizard's draft and save endpoints (#51).

The endpoints exist only where the bundled UI is served (ADR 0014), so these
tests build the app under patched settings, point it at a throwaway SQLite
datasource and write profiles into a temporary profiles directory. The saved
files are checked against the existing profile conformance test, so "one
contract, one loader" stays true.
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import sqlglot
from fastapi.testclient import TestClient

from test_profiles import TestSupportedProfileContract

SESSION_TABLE = "students"


@contextmanager
def app_client(mode: str, api_key: str, profiles_root: str, db_engine=None, nlp_engine=None):
    """Build the app under a settings patch and keep it active for requests.

    ``PROFILES_DIR`` is read at call time by both the writer and the demo state
    endpoint, so patching the module attribute isolates every test.
    """
    from api.main import create_app
    from api.dependencies import state_manager
    from core.config import settings
    import core.profiles as profiles_module

    previous_profiles_dir = profiles_module.PROFILES_DIR
    previous_db_engine = state_manager.db_engine
    previous_nlp_engine = state_manager.nlp_engine
    previous_profile = settings.DOMAIN_PROFILE
    profiles_module.PROFILES_DIR = profiles_root
    try:
        with (
            patch.object(settings, "APP_MODE", mode),
            patch.object(settings, "API_KEY", api_key),
            patch.object(settings, "DATABASE_URL", ""),
            patch.object(settings, "CORS_ORIGINS", "*"),
            patch.object(settings, "DOMAIN_PROFILE", "demo"),
        ):
            state_manager.db_engine = db_engine
            state_manager.nlp_engine = nlp_engine
            yield TestClient(create_app())
    finally:
        profiles_module.PROFILES_DIR = previous_profiles_dir
        state_manager.db_engine = previous_db_engine
        state_manager.nlp_engine = previous_nlp_engine
        settings.DOMAIN_PROFILE = previous_profile


def make_sqlite_engine(tmpdir: str):
    """A file-backed SQLite datasource with one small table."""
    path = os.path.join(tmpdir, "demo.db")
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            f"CREATE TABLE {SESSION_TABLE} (id INTEGER PRIMARY KEY, name TEXT)"
        )
        connection.executemany(
            f"INSERT INTO {SESSION_TABLE} (name) VALUES (?)",
            [("สมชาย",), ("สมหญิง",)],
        )
        connection.commit()
    finally:
        connection.close()

    from sqlalchemy import create_engine
    return create_engine(f"sqlite:///{path}"), path


def one_example(**overrides):
    payload = {
        "question": "จำนวนนักเรียนทั้งหมด",
        "sql": f"SELECT COUNT(*) AS total FROM {SESSION_TABLE}",
    }
    payload.update(overrides)
    return payload


def save(client: TestClient, name: str, **overrides):
    payload = {
        "name": name,
        "hints": "ปีการศึกษามีสองภาค",
        "schema_mappings": {"นักเรียน": [SESSION_TABLE]},
        "examples": [one_example()],
    }
    payload.update(overrides)
    return client.post("/api/demo/profile/save", json=payload)


class TestWizardRoutesAreDemoOnly(unittest.TestCase):
    def test_service_mode_has_no_wizard_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with app_client("service", "test-secret", os.path.join(tmpdir, "profiles")) as client:
                headers = {"X-API-Key": "test-secret"}
                self.assertEqual(
                    client.post(
                        "/api/demo/profile/draft",
                        json={"question": "กี่คน"},
                        headers=headers,
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    save(client, "school").status_code,
                    404,
                )

    def test_draft_needs_a_connected_datasource(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with app_client("demo", "", os.path.join(tmpdir, "profiles")) as client:
                response = client.post(
                    "/api/demo/profile/draft", json={"question": "กี่คน"}
                )
                self.assertEqual(response.status_code, 503)


class TestDraft(unittest.TestCase):
    def test_corrected_sql_is_executed_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                response = client.post(
                    "/api/demo/profile/draft",
                    json={
                        "question": "รายชื่อนักเรียน",
                        "sql": f"SELECT name FROM {SESSION_TABLE} ORDER BY name",
                    },
                )

                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body["status"], "ok")
                self.assertEqual(body["dialect"], "sqlite")
                self.assertEqual(body["row_count"], 2)
                self.assertEqual(body["rows"][0]["name"], "สมชาย")
                self.assertTrue(body["sql"].upper().startswith("SELECT"))
                self.assertTrue(os.path.isdir(root) is False or os.listdir(root) == [])

    def test_question_goes_through_the_service_generation_path(self):
        class FakeEngine:
            async def query_database(self, question, engine, dialect, **kwargs):
                return f"SELECT COUNT(*) AS n FROM {SESSION_TABLE}", [{"n": 2}], None, 0, None, 0

        with tempfile.TemporaryDirectory() as tmpdir:
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client(
                "demo", "", os.path.join(tmpdir, "profiles"),
                db_engine=engine, nlp_engine=FakeEngine(),
            ) as client:
                response = client.post(
                    "/api/demo/profile/draft", json={"question": "มีนักเรียนกี่คน"}
                )

                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(body["status"], "ok")
                self.assertEqual(body["category"], "count")
                self.assertEqual(body["rows"], [{"n": 2}])

    def test_read_only_violation_is_a_failure_not_a_saved_example(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", os.path.join(tmpdir, "profiles"), db_engine=engine) as client:
                response = client.post(
                    "/api/demo/profile/draft",
                    json={"question": "ลบนักเรียน", "sql": f"DELETE FROM {SESSION_TABLE}"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "error")
                self.assertIn("disallowed", response.json()["error"].lower())

    def test_unexecutable_sql_returns_the_failure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", os.path.join(tmpdir, "profiles"), db_engine=engine) as client:
                response = client.post(
                    "/api/demo/profile/draft",
                    json={"question": "ตารางที่ไม่มี", "sql": "SELECT * FROM missing_table"},
                )

                self.assertEqual(response.json()["status"], "error")
                self.assertIn("missing_table", response.json()["error"])


class TestSave(unittest.TestCase):
    def test_saves_the_full_file_set_with_service_supplied_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                response = save(
                    client, "my_school",
                    schema_mappings={"นักเรียน": [SESSION_TABLE], "จำนวน": ["COUNT"]},
                    examples=[
                        one_example(retrieval_tags=["นับนักเรียน", " "], grain="หนึ่งแถวต่อจำนวน"),
                        one_example(
                            question="รายชื่อนักเรียน",
                            sql=f"SELECT name FROM {SESSION_TABLE} ORDER BY name LIMIT 5",
                        ),
                    ],
                )

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    response.json()["coverage"],
                    {
                        "hints": True, "examples": 2, "exemplars": 0,
                        "schema_mappings": 2, "table_notes": 0,
                    },
                )

            directory = os.path.join(root, "my_school")
            self.assertEqual(
                sorted(os.listdir(directory)),
                ["examples.json", "hints.md", "schema_mappings.json"],
            )
            self.assertIn("ปีการศึกษามีสองภาค", open(
                os.path.join(directory, "hints.md"), encoding="utf-8").read())

            examples = json.load(open(
                os.path.join(directory, "examples.json"), encoding="utf-8"))["examples"]
            self.assertEqual([ex["id"] for ex in examples], ["wiz-001", "wiz-002"])
            self.assertTrue(all(ex["dialect"] == "sqlite" for ex in examples))
            self.assertEqual(examples[0]["category"], "count")
            self.assertEqual(examples[1]["category"], "ranking")
            self.assertEqual(examples[0]["retrieval_tags"], ["นับนักเรียน"])
            self.assertEqual(examples[0]["grain"], "หนึ่งแถวต่อจำนวน")

            mappings = json.load(open(
                os.path.join(directory, "schema_mappings.json"), encoding="utf-8"))
            self.assertEqual(mappings["นักเรียน"], [SESSION_TABLE])

    def test_empty_example_set_still_makes_the_profile_selectable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                response = save(client, "empty_profile", examples=[])

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["coverage"]["examples"], 0)
                self.assertTrue(
                    os.path.isfile(os.path.join(root, "empty_profile", "examples.json"))
                )
                self.assertIn("empty_profile", client.get("/api/demo/state").json()["profiles"])

    def test_slug_validation_rejects_bad_names_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                for name in ("../escape", "Bad Name", "a/b", ".hidden", "มีอักษรไทย"):
                    with self.subTest(name=name):
                        response = save(client, name)
                        self.assertEqual(response.status_code, 400, response.text)
                self.assertFalse(os.path.exists(os.path.join(tmpdir, "escape")))

    def test_existing_profile_is_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                self.assertEqual(save(client, "school").status_code, 200)

                refused = save(client, "school")
                self.assertEqual(refused.status_code, 409)
                self.assertIn("อยู่แล้ว", refused.json()["detail"])

                replaced = save(client, "school", hints="แก้ไขแล้ว", overwrite=True)
                self.assertEqual(replaced.status_code, 200, replaced.text)
                self.assertIn("แก้ไขแล้ว", open(
                    os.path.join(root, "school", "hints.md"), encoding="utf-8").read())

    def test_an_example_that_cannot_execute_blocks_the_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                response = save(
                    client, "broken",
                    examples=[one_example(sql="SELECT * FROM missing_table")],
                )

                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("รันไม่สำเร็จ", response.json()["detail"])
                self.assertFalse(os.path.exists(os.path.join(root, "broken")))

    def test_saved_examples_pass_the_existing_profile_conformance_test(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                self.assertEqual(save(client, "conform").status_code, 200)

            examples = json.load(open(
                os.path.join(root, "conform", "examples.json"), encoding="utf-8"))["examples"]
            checker = TestSupportedProfileContract()
            for example in examples:
                checker._assert_example_contract("conform", example)
                statements = sqlglot.parse(example["sql"], read="sqlite")
                self.assertEqual(len(statements), 1, example["id"])

    def test_follow_up_sections_are_written_and_counted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                response = save(
                    client, "deep",
                    table_notes={
                        SESSION_TABLE: {
                            "meaning": "หนึ่งแถวต่อนักเรียนหนึ่งคน",
                            "population": "เฉพาะนักเรียนที่ยังมีสถานะใช้งาน",
                        },
                    },
                    examples=[
                        one_example(),
                        {
                            "question": "ล่าสุดหมายถึงช่วงไหน",
                            "expected_answer_type": "clarification",
                            "expected_message": "ต้องการดูช่วงเวลาใดครับ — ภาคเรียนหรือวันที่",
                        },
                        {
                            "question": "ขอรายชื่อนักเรียนทุกคน",
                            "expected_answer_type": "refusal",
                            "expected_message": "ขออภัยครับ ระบบให้เฉพาะข้อมูลเชิงสถิติ",
                        },
                    ],
                )

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(
                    response.json()["coverage"],
                    {
                        "hints": True, "examples": 1, "exemplars": 2,
                        "schema_mappings": 1, "table_notes": 1,
                    },
                )

            directory = os.path.join(root, "deep")
            self.assertEqual(
                sorted(os.listdir(directory)),
                ["examples.json", "hints.md", "schema_mappings.json", "table_notes.json"],
            )
            notes = json.load(open(
                os.path.join(directory, "table_notes.json"), encoding="utf-8"))
            self.assertEqual(
                notes["tables"][SESSION_TABLE],
                {
                    "meaning": "หนึ่งแถวต่อนักเรียนหนึ่งคน",
                    "population": "เฉพาะนักเรียนที่ยังมีสถานะใช้งาน",
                },
            )

            examples = json.load(open(
                os.path.join(directory, "examples.json"), encoding="utf-8"))["examples"]
            self.assertEqual([ex["id"] for ex in examples], ["wiz-001", "wiz-002", "wiz-003"])
            clarification, refusal = examples[1], examples[2]
            self.assertEqual(clarification["sql"], "")
            self.assertEqual(clarification["category"], "clarification_exemplar")
            self.assertEqual(clarification["expected_answer_type"], "clarification")
            self.assertEqual(
                clarification["expected_message"],
                "ต้องการดูช่วงเวลาใดครับ — ภาคเรียนหรือวันที่",
            )
            self.assertEqual(refusal["category"], "refusal_exemplar")
            self.assertEqual(refusal["expected_answer_type"], "refusal")

            checker = TestSupportedProfileContract()
            for example in examples:
                checker._assert_example_contract("deep", example)

    def test_an_exemplar_needs_a_message_and_must_not_carry_sql(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                for label, exemplar in {
                    "missing message": {
                        "question": "ขอรายชื่อนักเรียน",
                        "expected_answer_type": "refusal",
                    },
                    "carries sql": {
                        "question": "ขอรายชื่อนักเรียน",
                        "sql": f"SELECT name FROM {SESSION_TABLE}",
                        "expected_answer_type": "refusal",
                        "expected_message": "ไม่สามารถแสดงข้อมูลส่วนบุคคลได้",
                    },
                }.items():
                    with self.subTest(label=label):
                        response = save(client, "bad", examples=[exemplar])
                        self.assertEqual(response.status_code, 400, response.text)
            self.assertFalse(os.path.exists(os.path.join(root, "bad")))

    def test_incomplete_table_note_blocks_the_save(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                response = save(
                    client, "partial",
                    table_notes={SESSION_TABLE: {"meaning": "หนึ่งแถวต่อคน", "population": " "}},
                )

                self.assertEqual(response.status_code, 400, response.text)
                self.assertIn("กลุ่มข้อมูล", response.json()["detail"])
            self.assertFalse(os.path.exists(os.path.join(root, "partial")))

    def test_overwrite_without_the_follow_up_pass_removes_stale_table_notes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, _ = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                first = save(
                    client, "deep",
                    table_notes={SESSION_TABLE: {"meaning": "ก", "population": "ข"}},
                )
                self.assertEqual(first.status_code, 200, first.text)

                second = save(client, "deep", overwrite=True)
                self.assertEqual(second.status_code, 200, second.text)
                self.assertEqual(second.json()["coverage"]["table_notes"], 0)
            self.assertFalse(
                os.path.isfile(os.path.join(root, "deep", "table_notes.json"))
            )

    def test_saved_profile_switches_at_runtime_without_a_restart(self):
        from api.dependencies import state_manager

        with tempfile.TemporaryDirectory() as tmpdir:
            root = os.path.join(tmpdir, "profiles")
            engine, path = make_sqlite_engine(tmpdir)
            with app_client("demo", "", root, db_engine=engine) as client:
                self.assertEqual(save(client, "fresh").status_code, 200)
                state_manager.nlp_engine = None  # no warm rebuild in a unit test

                response = client.post(
                    "/api/demo/connect",
                    json={"database_url": f"sqlite:///{path}", "profile": "fresh"},
                )

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["profile"], "fresh")
                self.assertEqual(client.get("/api/demo/state").json()["profile"], "fresh")


if __name__ == "__main__":
    unittest.main()
