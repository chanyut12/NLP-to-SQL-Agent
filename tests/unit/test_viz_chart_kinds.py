"""Chart-kind catalog tests (ticket #52, ADR 0015) at the VizService seam.

DataFrame in, config out — the same entry point the engine uses. These pin the
rules that decide a kind, the form and the sort, and the invariant that every
alternative offered is a key the renderer implements.
"""
import pandas as pd
import pytest
from langchain_core.runnables import RunnableLambda

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


def df_heatmap() -> pd.DataFrame:
    """Six schools x four risk tiers: a dense two-dimension grid (24 cells)."""
    tiers = ["สูง", "เฝ้าระวัง", "ปกติ", "ไม่ประเมิน"]
    return pd.DataFrame([
        {"school_name": f"โรงเรียน{i}", "risk_tier": tier, "student_count": 10 + i}
        for i in range(6) for tier in tiers
    ])


def df_one_to_one_labels() -> pd.DataFrame:
    """Two label columns where one merely names the other — a diagonal, not a
    matrix (many cells, but no shared levels)."""
    n = 13
    return pd.DataFrame({
        "rule_code": [f"RULE_{i:02d}" for i in range(n)],
        "rule_reason": [f"เหตุผลที่ {i}" for i in range(n)],
        "signal_count": list(range(1, n + 1)),
    })


def df_no_label() -> pd.DataFrame:
    return pd.DataFrame({"student_id": [101, 102], "attendance_count": [12, 8]})


def df_raw_rows() -> pd.DataFrame:
    """Raw observations of one measure — no group, so a histogram of the spread."""
    return pd.DataFrame({"gpax": [2.5, 3.1, 2.8, 3.9, 2.2, 3.4, 3.0, 2.6]})


def df_raw_rows_by_school() -> pd.DataFrame:
    """Raw rows with a repeated category: a histogram with a boxplot per school."""
    rows = []
    for school, values in (("ก", (2.5, 3.1, 2.8, 3.0)),
                           ("ข", (3.9, 2.2, 3.4, 2.7)),
                           ("ค", (2.0, 2.7, 3.8, 3.2))):
        rows += [{"school_name": school, "gpax": v} for v in values]
    return pd.DataFrame(rows)


def df_aggregate_count() -> pd.DataFrame:
    """`GROUP BY class` — one row per group, so there is no distribution."""
    return pd.DataFrame({
        "class_name": ["ม.1", "ม.2", "ม.3", "ม.4", "ม.5", "ม.6"],
        "count": [30, 25, 28, 31, 22, 27],
    })


def df_aggregate_count_alias() -> pd.DataFrame:
    """`GROUP BY department` with the count aliased `c`: the shape says
    aggregate even though the name says nothing."""
    return pd.DataFrame({
        "department": ["ขาย", "คลัง", "personnel", "zh", "it", "บุคคล"],
        "c": [3, 4, 5, 6, 7, 8],
    })


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
                   df_two_numbers(), df_no_label(), df_heatmap(),
                   df_one_to_one_labels()):
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


class TestHeatmap:
    """Two category dimensions cross into a matrix; a dense one reads as color
    (ticket #53). Sparse grids and ordered axes stay in the bar/line family."""

    def test_two_dense_dimensions_recommend_a_heatmap(self):
        cfg = svc().recommend(df_heatmap(), "จำนวนนักเรียนแยกตามโรงเรียนและระดับความเสี่ยง")
        assert cfg["chart_type"] == "heatmap"
        assert cfg["x_col"] == "school_name"
        assert cfg["series_col"] == "risk_tier"
        assert cfg["y_col"] == "student_count"
        assert cfg["chart_form"] is None
        assert cfg["y2_col"] is None
        assert cfg["reason"]

    def test_heatmap_is_offered_and_the_bar_family_stays_available(self):
        cfg = svc().recommend(df_heatmap(), "")
        assert "heatmap" in cfg["options"]
        assert {"bar_grouped", "bar_stacked"} <= set(cfg["options"])
        assert cfg["chart_type"] in cfg["options"]

    def test_a_small_matrix_stays_grouped_bars(self):
        cfg = svc().recommend(df_series(equal_totals=False), "จำนวนนักเรียนแยกตามโรงเรียน")
        assert cfg["chart_type"] == "bar_grouped"
        # Drawable, so still offered as an alternative.
        assert "heatmap" in cfg["options"]

    def test_heatmap_needs_both_dimensions_to_cross(self):
        cfg = svc().recommend(df_one_to_one_labels(), "สาเหตุของความเสี่ยง")
        assert cfg["chart_type"] != "heatmap"
        assert "heatmap" not in cfg["options"]

    def test_an_ordered_axis_is_a_trend_not_a_heatmap(self):
        df = pd.DataFrame({
            "month_label": ["ม.ค.", "ก.พ.", "มี.ค."] * 4,
            "school_name": [f"โรงเรียน{i}" for i in range(4)] * 3,
            "count": list(range(12)),
        })
        cfg = svc().recommend(df, "จำนวนรายเดือน")
        assert cfg["chart_type"] != "heatmap"
        assert "heatmap" not in cfg["options"]

    def test_one_dimension_never_offers_a_heatmap(self):
        cfg = svc().recommend(df_plain_bar(), "จำนวนนักเรียน")
        assert "heatmap" not in cfg["options"]


class TestTreemap:
    """A treemap is offered for one high-cardinality category with additive,
    positive measures — and refused when the parts would misstate the whole."""

    def test_high_cardinality_positive_count_offers_a_treemap(self):
        cfg = svc().recommend(df_long_axis(), "จำนวนนักเรียนแยกตามโรงเรียน")
        assert cfg["chart_type"] == "bar_horizontal"   # the bar stays the default
        assert "treemap" in cfg["options"]

    def test_treemap_can_be_requested_and_states_its_sort(self):
        cfg = svc().recommend(df_long_axis(), "", "treemap")
        assert cfg["chart_type"] == "treemap"
        assert cfg["x_col"] == "school_name"
        assert cfg["y_col"] == "student_count"
        assert cfg["series_col"] is None
        assert cfg["sort"] == "value_desc"
        assert "treemap" in cfg["options"]

    def test_a_negative_measure_is_not_a_treemap(self):
        df = df_long_axis()
        df.loc[0, "student_count"] = -5
        cfg = svc().recommend(df, "จำนวนนักเรียนแยกตามโรงเรียน")
        assert "treemap" not in cfg["options"]
        assert svc().recommend(df, "", "treemap")["chart_type"] != "treemap"

    def test_a_non_additive_measure_is_not_a_treemap(self):
        df = pd.DataFrame({
            "school_name": [f"โรงเรียน{i}" for i in range(13)],
            "attendance_rate_percent": [80.0 + i for i in range(13)],
        })
        cfg = svc().recommend(df, "อัตราการมาเรียนแยกตามโรงเรียน")
        assert "treemap" not in cfg["options"]

    def test_a_small_category_set_is_not_a_treemap(self):
        assert "treemap" not in svc().recommend(df_plain_bar(), "")["options"]


class TestDistributionViews:
    """Raw rows carry a distribution; an aggregate already holds one row per
    group and never gets one (ticket #54)."""

    def test_raw_numeric_rows_recommend_a_histogram(self):
        cfg = svc().recommend(df_raw_rows(), "เกรดเฉลี่ยเป็นอย่างไร")
        assert cfg["chart_type"] == "histogram"
        assert cfg["y_col"] == "gpax"
        assert cfg["x_col"] is None
        assert cfg["options"] == ["histogram", "table"]
        assert cfg["reason"]

    def test_a_repeated_category_offers_a_boxplot_per_category(self):
        cfg = svc().recommend(df_raw_rows_by_school(), "การกระจายของเกรดนักเรียน")
        assert cfg["chart_type"] == "histogram"
        assert cfg["y_col"] == "gpax"
        assert "boxplot" in cfg["options"]
        # The group rides along so switching to the boxplot needs no new request.
        assert cfg["x_col"] == "school_name"

    def test_boxplot_can_be_requested_and_keeps_its_group(self):
        cfg = svc().recommend(df_raw_rows_by_school(), "", "boxplot")
        assert cfg["chart_type"] == "boxplot"
        assert cfg["x_col"] == "school_name"
        assert cfg["y_col"] == "gpax"
        assert cfg["chart_form"] is None
        assert cfg["sort"] is None

    def test_bar_family_is_not_offered_for_raw_rows(self):
        offered = svc().recommend(df_raw_rows_by_school(), "")["options"]
        assert "bar" not in offered
        assert "line" not in offered
        assert "pie" not in offered

    def test_count_per_group_is_not_a_distribution(self):
        cfg = svc().recommend(df_aggregate_count(), "จำนวนนักเรียนแยกตามห้อง")
        assert cfg["chart_type"] == "bar"
        assert "histogram" not in cfg["options"]
        assert "boxplot" not in cfg["options"]

    def test_an_aggregate_alias_is_refused_by_shape(self):
        # `c` is not an aggregate-sounding name, but one row per department with
        # an integer column is a `GROUP BY` count, not a measurement.
        cfg = svc().recommend(df_aggregate_count_alias(), "จำนวนแยกตามแผนก")
        assert cfg["chart_type"] == "bar"
        assert "histogram" not in cfg["options"]

    def test_a_summed_alias_is_refused_by_name(self):
        df = pd.DataFrame({
            "product_category": ["เสื้อ", "อาหาร", "เครื่องใช้", "อิเล็ก", "ของใช้"],
            "revenue": [1000.5, 2200.0, 1800.25, 3000.0, 950.75],
        })
        cfg = svc().recommend(df, "ยอดขายแยกตามหมวดสินค้า")
        assert cfg["chart_type"] == "bar"
        assert "histogram" not in cfg["options"]

    def test_a_per_row_measure_with_a_repeated_label_is_raw(self):
        # `total_price` per receipt: the name sounds aggregate, but the repeated
        # category says these are observations, so the distribution stands.
        rows = [{"product_category": c, "total_price": p}
                for c, p in (("เสื้อ", 120.5), ("เสื้อ", 340.0), ("เสื้อ", 90.25),
                             ("อาหาร", 60.0), ("อาหาร", 210.5), ("อาหาร", 75.0),
                             ("ของใช้", 400.0), ("ของใช้", 150.0), ("ของใช้", 320.5))]
        cfg = svc().recommend(pd.DataFrame(rows), "ราคาต่อใบเสร็จ")
        assert cfg["chart_type"] == "histogram"
        assert "boxplot" in cfg["options"]

    def test_two_measures_are_not_a_distribution(self):
        cfg = svc().recommend(df_two_numbers(), "ความสัมพันธ์")
        assert cfg["chart_type"] == "scatter"
        assert "histogram" not in cfg["options"]

    def test_a_constant_measure_degrades_to_a_table(self):
        df = df_raw_rows().assign(gpax=[3.0] * 8)
        cfg = svc().recommend(df, "เกรดเฉลี่ย")
        assert cfg["chart_type"] == "table"
        assert cfg["options"] == ["table"]
        assert "ตาราง" in cfg["reason"]

    def test_too_few_rows_are_not_a_distribution(self):
        df = pd.DataFrame({"gpax": [2.5, 3.1, 2.8]})
        cfg = svc().recommend(df, "เกรด")
        assert cfg["chart_type"] != "histogram"
        assert "histogram" not in cfg["options"]

    def test_empty_result_stays_empty(self):
        assert svc().recommend(pd.DataFrame(), "เกรด")["chart_type"] == "none"


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

    def test_ai_heatmap_without_two_dimensions_degrades_to_bar(self):
        # A real Runnable, so the intelligent path actually runs and the guard —
        # not the rule-based fallback — is what repairs the config.
        llm = RunnableLambda(lambda _: (
            '{"chart_type": "heatmap", "title": "t", '
            '"x_col": "class_name", "y_col": "count", "reason": "r"}'))

        cfg = VizService(llm=llm, enable_intelligent=True).recommend(
            df_plain_bar(), "จำนวนนักเรียน")
        assert cfg["chart_type"] == "bar"
        assert cfg["series_col"] is None

    def test_ai_treemap_over_a_percent_measure_degrades_to_bar(self):
        df = pd.DataFrame({
            "school_name": [f"โรงเรียน{i}" for i in range(13)],
            "attendance_rate_percent": [80.0 + i for i in range(13)],
        })

        llm = RunnableLambda(lambda _: (
            '{"chart_type": "treemap", "title": "t", '
            '"x_col": "school_name", "y_col": "attendance_rate_percent", '
            '"reason": "r"}'))

        cfg = VizService(llm=llm, enable_intelligent=True).recommend(df, "อัตราการมาเรียน")
        assert cfg["chart_type"] == "bar"


@pytest.mark.parametrize("kind,df", [
    ("bar", df_plain_bar()),
    ("bar_horizontal", df_long_axis()),
    ("bar_grouped", df_series(equal_totals=False)),
    ("bar_stacked", df_series(equal_totals=True)),
    ("bar_stacked_100", df_series_percent()),
    ("line", df_plain_bar()),
    ("area", df_plain_bar()),
    ("combo", df_combo()),
    ("heatmap", df_heatmap()),
    ("treemap", df_long_axis()),
    ("histogram", df_raw_rows_by_school()),
    ("boxplot", df_raw_rows_by_school()),
])
def test_every_offered_kind_is_recommended_not_degraded(kind, df):
    """Asking for a catalog kind the grid supports returns that kind, and the
    alternatives still contain it — the renderability invariant."""
    cfg = svc().recommend(df, "จำนวนนักเรียนและอัตราการมาเรียน", kind)
    assert cfg["chart_type"] == kind
    assert kind in cfg["options"]
