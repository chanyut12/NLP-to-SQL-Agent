"""Chart-kind catalog tests (ticket #52, ADR 0015) at the VizService seam.

DataFrame in, config out — the same entry point the engine uses. These pin the
rules that decide a kind, the form and the sort, and the invariant that every
alternative offered is a key the renderer implements.
"""
import pandas as pd
import pytest

from core.viz.viz_recommender import (
    CHART_KINDS, SERIES_FORMS, SORT_ORDERS, VizService,
)


def svc() -> VizService:
    # Production rule-based configuration: no LLM, intelligent off.
    return VizService()


def df_plain_bar() -> pd.DataFrame:
    return pd.DataFrame({"class_name": ["ม.1", "ม.2"], "count": [30, 25]})


def df_long_axis() -> pd.DataFrame:
    n = 13
    return pd.DataFrame({
        "school_name": [f"โรงเรียน{i:02d}" for i in range(n)],
        "student_count": list(range(100, 100 + n)),
    })


def df_series(equal_totals: bool) -> pd.DataFrame:
    """Three schools split by region: a part-to-whole when each school's total
    is the same, unrelated series when the totals differ."""
    third = 9 if equal_totals else 12
    return pd.DataFrame({
        "school_name": ["โรงเรียน ก", "โรงเรียน ก", "โรงเรียน ข", "โรงเรียน ข",
                        "โรงเรียน ค", "โรงเรียน ค"],
        "region": ["เหนือ", "ใต้"] * 3,
        "student_count": [10, 5, 8, 7, third, 6],
    })


def df_series_percent() -> pd.DataFrame:
    return pd.DataFrame({
        "school_name": ["โรงเรียน ก", "โรงเรียน ก", "โรงเรียน ข", "โรงเรียน ข"],
        "region": ["เหนือ", "ใต้"] * 2,
        "attendance_rate_percent": [82.0, 18.0, 85.0, 15.0],
    })


def df_combo() -> pd.DataFrame:
    return pd.DataFrame({
        "province_name": ["ตรัง", "พัทลุง", "สงขลา"],
        "student_count": [1200, 980, 1540],
        "attendance_rate_percent": [78.5, 82.1, 74.2],
    })


def df_two_numbers() -> pd.DataFrame:
    return pd.DataFrame({
        "student_count": [100, 200, 300],
        "absent_count": [4, 9, 12],
    })


def df_no_label() -> pd.DataFrame:
    return pd.DataFrame({"student_id": [101, 102], "attendance_count": [12, 8]})


class TestKindsAreKeys:
    def test_options_are_chart_kind_keys_not_labels(self):
        cfg = svc().recommend(df_plain_bar(), "จำนวนนักเรียนแยกตามห้อง")
        assert cfg["options"]
        assert set(cfg["options"]) <= set(CHART_KINDS)
        assert "Bar Chart" not in cfg["options"]
        assert cfg["chart_type"] in cfg["options"]

    def test_every_fixture_offers_only_chart_kinds(self):
        for df in (df_plain_bar(), df_long_axis(), df_series(True),
                   df_series(False), df_series_percent(), df_combo(),
                   df_two_numbers(), df_no_label()):
            cfg = svc().recommend(df, "")
            assert set(cfg["options"]) <= set(CHART_KINDS), cfg["options"]
            assert cfg["chart_type"] in CHART_KINDS
            if cfg["chart_type"] not in ("none", "table"):
                assert cfg["chart_type"] in cfg["options"]


class TestBarFamily:
    def test_plain_category_measure_is_a_vertical_bar_sorted_by_value(self):
        cfg = svc().recommend(df_plain_bar(), "จำนวนนักเรียนแยกตามห้อง")
        assert cfg["chart_type"] == "bar"
        assert cfg["sort"] == "value_desc"
        assert cfg["chart_form"] is None

    def test_long_category_axis_turns_horizontal(self):
        cfg = svc().recommend(df_long_axis(), "จำนวนนักเรียนแยกตามโรงเรียน")
        assert cfg["chart_type"] == "bar_horizontal"
        assert cfg["sort"] == "value_desc"
        assert cfg["top_n"] == 12

    def test_explicit_bar_preference_stays_vertical(self):
        cfg = svc().recommend(df_long_axis(), "จำนวนนักเรียน", "bar")
        assert cfg["chart_type"] == "bar"


class TestSeriesForm:
    """Grouped vs stacked vs 100% is decided by rules, not by the renderer."""

    def test_independent_series_is_grouped(self):
        cfg = svc().recommend(df_series(equal_totals=False), "จำนวนนักเรียนแยกตามโรงเรียน")
        assert cfg["chart_type"] == "bar_grouped"
        assert cfg["chart_form"] == "grouped"
        assert cfg["series_col"] == "region"

    def test_parts_that_share_a_total_stack(self):
        cfg = svc().recommend(df_series(equal_totals=True), "จำนวนนักเรียนแยกตามโรงเรียน")
        assert cfg["chart_type"] == "bar_stacked"
        assert cfg["chart_form"] == "stacked"

    def test_percent_measure_stacks_to_one_hundred(self):
        cfg = svc().recommend(df_series_percent(), "อัตราการมาเรียนแยกตามโรงเรียน")
        assert cfg["chart_type"] == "bar_stacked_100"
        assert cfg["chart_form"] == "stacked_100"

    def test_form_values_are_the_contract_vocabulary(self):
        for df in (df_series(True), df_series(False), df_series_percent()):
            cfg = svc().recommend(df, "จำนวนนักเรียนแยกตามโรงเรียน")
            assert cfg["chart_form"] in SERIES_FORMS
            assert cfg["sort"] in SORT_ORDERS

    def test_explicit_series_form_is_honoured(self):
        cfg = svc().recommend(
            df_series(equal_totals=False), "จำนวนนักเรียนแยกตามโรงเรียน", "bar_stacked")
        assert cfg["chart_type"] == "bar_stacked"
        assert cfg["chart_form"] == "stacked"

    def test_series_form_without_a_series_role_degrades_to_bar(self):
        cfg = svc().recommend(df_plain_bar(), "จำนวนนักเรียน", "bar_grouped")
        assert cfg["chart_type"] == "bar"
        assert cfg["chart_form"] is None


class TestCombo:
    def test_count_and_rate_pair_recommends_combo(self):
        cfg = svc().recommend(df_combo(), "จำนวนนักเรียนและอัตราการมาเรียนรายจังหวัด")
        assert cfg["chart_type"] == "combo"
        assert cfg["y_col"] == "student_count"
        assert cfg["y2_col"] == "attendance_rate_percent"
        assert cfg["series_col"] is None

    def test_combo_is_offered_and_states_its_sort(self):
        cfg = svc().recommend(df_combo(), "จำนวนนักเรียนและอัตราการมาเรียน")
        assert "combo" in cfg["options"]
        assert cfg["sort"] in SORT_ORDERS

    def test_two_counts_do_not_make_a_combo(self):
        cfg = svc().recommend(
            pd.DataFrame({"class_name": ["ม.1", "ม.2"], "student_count": [30, 25],
                          "teacher_count": [3, 2]}),
            "จำนวนนักเรียนและครู")
        assert cfg["chart_type"] == "bar"
        assert cfg["y2_col"] is None


class TestAlternativesAreDerived:
    def test_series_result_offers_the_bar_family_and_not_pie(self):
        cfg = svc().recommend(df_series(equal_totals=True), "จำนวนนักเรียนรายเดือน")
        offered = set(cfg["options"])
        assert {"bar_grouped", "bar_stacked", "bar_stacked_100"} <= offered
        assert "pie" not in offered

    def test_single_series_result_offers_pie_and_both_orientations(self):
        offered = set(svc().recommend(df_plain_bar(), "จำนวนนักเรียน")["options"])
        assert {"bar", "bar_horizontal", "line", "area", "pie", "table"} <= offered

    def test_two_measures_offer_scatter(self):
        offered = set(svc().recommend(df_two_numbers(), "ความสัมพันธ์")["options"])
        assert "scatter" in offered

    def test_thin_result_offers_table_only(self):
        cfg = svc().recommend(df_no_label(), "จำนวนการขาดเรียนต่อนักเรียน")
        assert cfg["chart_type"] == "table"
        assert cfg["options"] == ["table"]


class TestExitGuardStillRules:
    def test_not_chartable_result_clears_chart_only_fields(self):
        cfg = svc().recommend(df_no_label(), "จำนวนการขาดเรียนต่อนักเรียน")
        assert cfg["x_col"] is None
        assert cfg["y_col"] is None
        assert cfg["chart_form"] is None
        assert cfg["sort"] is None
        assert cfg["y2_col"] is None

    def test_ai_path_cannot_emit_an_undrawable_series_kind(self):
        class FakeLLM:
            def invoke(self, *_args, **_kwargs):
                return ('{"chart_type": "bar_stacked_100", "title": "t", '
                        '"x_col": "class_name", "y_col": "count", "reason": "r"}')

        cfg = VizService(llm=FakeLLM(), enable_intelligent=True).recommend(
            df_plain_bar(), "จำนวนนักเรียน")
        assert cfg["chart_type"] == "bar"      # no series role -> degraded
        assert cfg["chart_form"] is None


@pytest.mark.parametrize("kind,df", [
    ("bar", df_plain_bar()),
    ("bar_horizontal", df_long_axis()),
    ("bar_grouped", df_series(equal_totals=False)),
    ("bar_stacked", df_series(equal_totals=True)),
    ("bar_stacked_100", df_series_percent()),
    ("line", df_plain_bar()),
    ("area", df_plain_bar()),
    ("combo", df_combo()),
])
def test_every_offered_kind_is_recommended_not_degraded(kind, df):
    """Asking for a catalog kind the grid supports returns that kind, and the
    alternatives still contain it — the renderability invariant."""
    cfg = svc().recommend(df, "จำนวนนักเรียนและอัตราการมาเรียน", kind)
    assert cfg["chart_type"] == kind
    assert kind in cfg["options"]
