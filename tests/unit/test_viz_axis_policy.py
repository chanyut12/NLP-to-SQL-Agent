"""Axis-selection policy tests (ADR 0008) at the single production seam.

Every test drives VizService.recommend — the same entry point the engine uses —
with a plain DataFrame in and a viz config out. No LLM, no DB. Prior art:
tests/unit/test_column_meta.py (DataFrame in, dict out, no I/O).
"""
import pandas as pd
import pytest

from core.viz.viz_recommender import VizService


def svc() -> VizService:
    # Production rule-based configuration: no LLM, intelligent off.
    return VizService()


def df_id_name_metric() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "student_id": [101, 102, 103],
            "student_name": ["แดง", "มะลิ", "ปอนด์"],
            "attendance_count": [12, 8, 15],
        }
    )


class TestIdNeverLabelsAnAxis:
    @pytest.mark.parametrize("preferred", [None, "bar", "pie", "line", "scatter"])
    def test_id_name_metric_uses_name_as_axis(self, preferred):
        cfg = svc().recommend(
            df_id_name_metric(), "จำนวนการขาดเรียนแยกตามนักเรียน", preferred
        )
        assert cfg["x_col"] == "student_name"
        assert cfg["x_col"] != "student_id"

    def test_name_preferred_over_category(self):
        df = pd.DataFrame(
            {
                "room_id": [1, 2],
                "room_name": ["ห้อง A", "ห้อง B"],
                "room_type": ["ทั่วไป", "พิเศษ"],
                "count": [5, 7],
            }
        )
        cfg = svc().recommend(df, "จำนวนแยกตามห้อง")
        assert cfg["x_col"] == "room_name"

    def test_category_falls_back_when_no_name(self):
        df = pd.DataFrame(
            {
                "room_id": [1, 2, 3],
                "room_type": ["ทั่วไป", "พิเศษ", "ทั่วไป"],
                "count": [5, 7, 2],
            }
        )
        cfg = svc().recommend(df, "จำนวนแยกตามประเภทห้อง")
        assert cfg["x_col"] == "room_type"

    def test_time_axis_still_wins_for_line(self):
        df = pd.DataFrame({"month": [1, 2, 3], "count": [5, 7, 2]})
        cfg = svc().recommend(df, "จำนวนรายเดือน")
        assert cfg["chart_type"] == "line"
        assert cfg["x_col"] == "month"


class TestNotChartable:
    def test_id_only_plus_metric_becomes_table(self):
        df = pd.DataFrame({"student_id": [101, 102], "attendance_count": [12, 8]})
        cfg = svc().recommend(df, "จำนวนการขาดเรียนต่อนักเรียน")
        assert cfg["chart_type"] == "table"
        assert "ชื่อ" in (cfg.get("reason") or "")

    def test_id_only_axis_label_cleared(self):
        df = pd.DataFrame({"student_id": [101, 102], "attendance_count": [12, 8]})
        cfg = svc().recommend(df, "จำนวนการขาดเรียนต่อนักเรียน")
        assert cfg["x_col"] is None
        assert cfg["x_label"] is None


class TestRegression:
    def test_plain_category_metric_bar_unchanged(self):
        df = pd.DataFrame({"class_name": ["ม.1", "ม.2"], "count": [30, 25]})
        cfg = svc().recommend(df, "จำนวนนักเรียนแยกตามห้อง")
        assert cfg["chart_type"] == "bar"
        assert cfg["x_col"] == "class_name"

    def test_top_n_computed_on_new_axis(self):
        n = 20
        df = pd.DataFrame(
            {
                "student_id": range(100, 100 + n),
                "student_name": [f"นักเรียน{i:02d}" for i in range(n)],
                "count": list(range(n)),
            }
        )
        cfg = svc().recommend(df, "จำนวนแยกตามนักเรียน", "bar")
        assert cfg["x_col"] == "student_name"
        assert cfg["top_n"] == 12


class TestExitGuard:
    """The policy is a guard, not a suggestion path (ADR 0008 decision 4):
    even a config produced by the (currently disabled) AI recommender must
    come out compliant."""

    @staticmethod
    def fake_llm_returning(x_col: str):
        class FakeLLM:
            def invoke(self, *_args, **_kwargs):
                return (
                    '{"chart_type": "bar", "title": "t", "x_col": "%s", '
                    '"y_col": "attendance_count", "reason": "r"}' % x_col
                )

        return FakeLLM()

    def test_guard_fixes_id_axis_from_ai_path(self):
        s = VizService(llm=self.fake_llm_returning("student_id"), enable_intelligent=True)
        cfg = s.recommend(df_id_name_metric(), "จำนวนการขาดเรียนแยกตามนักเรียน")
        assert cfg["x_col"] == "student_name"
        assert cfg["x_label"] == "student name"

    def test_guard_falls_back_to_table_when_no_name(self):
        s = VizService(llm=self.fake_llm_returning("student_id"), enable_intelligent=True)
        df = pd.DataFrame({"student_id": [101, 102], "attendance_count": [12, 8]})
        cfg = s.recommend(df, "จำนวนการขาดเรียนต่อนักเรียน")
        assert cfg["chart_type"] == "table"


def df_risk_signals_by_rule() -> pd.DataFrame:
    # The Oct 2026 log 8a076241: one source system, four rules. Charting the
    # source column gave four bars all labelled SUBJECT_RISK_MONITOR.
    return pd.DataFrame(
        {
            "signal_source_code": ["SUBJECT_RISK_MONITOR"] * 4,
            "signal_rule_code": [
                "LOW_ATTENDANCE_PERCENT",
                "MIXED_SUBJECT_ABSENCE",
                "TERM_ABSENCE_ACCUMULATION",
                "SUBJECT_AVOIDANCE_PERCENT",
            ],
            "signal_count": [4, 4, 2, 1],
            "example_reason": [
                "เวลาเรียนต่ำกว่าเกณฑ์: มาเรียน 64% (ต่ำกว่า 80%)",
                "โดดคาบ: มาเรียนบางคาบแต่ขาดบางคาบ 3 วัน (เกณฑ์ 3 วัน)",
                "ขาดสะสมต่อเทอม 7 วัน (เกณฑ์ 7 วัน)",
                "เลี่ยงวิชาเดิม: ขาดวิชาการงานอาชีพ (CAREER) 38%",
            ],
        }
    )


class TestConstantColumnNeverLabelsAnAxis:
    """A label column with one value across many rows gives bars that all
    share one name — it carries no axis information."""

    @pytest.mark.parametrize("preferred", [None, "bar", "pie"])
    def test_rule_code_labels_the_axis_not_the_single_source(self, preferred):
        cfg = svc().recommend(
            df_risk_signals_by_rule(), "สาเหตุของความเสี่ยงเกิดจากอะไร", preferred
        )
        assert cfg["x_col"] == "signal_rule_code"

    def test_guard_fixes_constant_axis_from_ai_path(self):
        class FakeLLM:
            def invoke(self, *_args, **_kwargs):
                return (
                    '{"chart_type": "bar", "title": "t", "x_col": "signal_source_code", '
                    '"y_col": "signal_count", "reason": "r"}'
                )

        s = VizService(llm=FakeLLM(), enable_intelligent=True)
        cfg = s.recommend(df_risk_signals_by_rule(), "สาเหตุของความเสี่ยงเกิดจากอะไร")
        assert cfg["x_col"] == "signal_rule_code"

    def test_single_row_keeps_its_only_label(self):
        df = pd.DataFrame({"signal_rule_code": ["LOW_ATTENDANCE_PERCENT"], "signal_count": [4]})
        cfg = svc().recommend(df, "สาเหตุของความเสี่ยง")
        assert cfg["x_col"] == "signal_rule_code"

    def test_reason_labels_the_axis_when_rules_repeat(self):
        # Live run after the fix: grouped by source, rule AND reason -> 8 rows,
        # 4 rule codes. Only signal_reason names each bar uniquely.
        df = pd.DataFrame(
            {
                "signal_source_code": ["SUBJECT_RISK_MONITOR"] * 4,
                "signal_rule_code": [
                    "MIXED_SUBJECT_ABSENCE", "LOW_ATTENDANCE_PERCENT",
                    "LOW_ATTENDANCE_PERCENT", "TERM_ABSENCE_ACCUMULATION",
                ],
                "signal_reason": [
                    "โดดคาบ: มาเรียนบางคาบแต่ขาดบางคาบ 3 วัน (เกณฑ์ 3 วัน)",
                    "เวลาเรียนต่ำกว่าเกณฑ์: มาเรียน 64% (ต่ำกว่า 80%)",
                    "เวลาเรียนต่ำกว่าเกณฑ์: มาเรียน 74% (ต่ำกว่า 80%)",
                    "ขาดสะสมต่อเทอม 8 วัน (เกณฑ์ 7 วัน)",
                ],
                "signal_count": [4, 1, 1, 1],
            }
        )
        cfg = svc().recommend(df, "สาเหตุของความเสี่ยงเกิดจากอะไร")
        assert cfg["x_col"] == "signal_reason"

    def test_value_axis_skips_a_total_repeated_on_every_row(self):
        # Risk-factor answer: per-factor count beside slice-wide totals.
        df = pd.DataFrame(
            {
                "factor": ["มาเรียนต่ำกว่า 80%", "ขาดติดต่อกันตั้งแต่ 3 วัน", "มาสาย"],
                "high_risk_students": [75, 75, 12],
                "high_risk_total": [77, 77, 77],
                "recorded_signal_count": [1, 1, 1],
            }
        )
        cfg = svc().recommend(df, "ทำไมจังหวัดตรังจึงน่าเป็นห่วงที่สุด เพราะอะไร")
        assert (cfg["x_col"], cfg["y_col"]) == ("factor", "high_risk_students")


