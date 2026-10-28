"""
Visualization Recommender System.
Analyzes DataFrame content to suggest the best chart type.

Axis-selection policy (ADR 0008, extending ADR 0004's semantic types): a column
whose semantic type is `id` never labels a chart axis; identifier–name pairs
resolve to the name; a result with no axis label column (name → category → text)
is not chartable and renders as a table. Enforced inside the rule-based
recommender AND as an exit guard on VizService.recommend so no recommender
(including the disabled AI one) can emit an id axis.
"""
import pandas as pd
from typing import Tuple, Optional, List, Dict, Any

from core.viz.column_meta import _column_info
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser


def detect_series_column(df: pd.DataFrame, x_col: Optional[str], y_col: Optional[str]) -> Optional[str]:
    """
    Detect if the data should be split into multiple series (e.g., year+month → line per year).
    
    Returns the column name to use as series grouper, or None if single-series.
    
    Rule-based detection for common patterns:
    - If x_col is month/quarter/week AND there's a year column → group by year
    - If x_col is year AND there's a month column → group by month (swap logic)
    - If x_col is day AND there's a month column → group by month
    """
    if df.empty or not x_col:
        return None
    
    columns = [c.lower() for c in df.columns]
    x_lower = x_col.lower()
    
    # Define term lists
    month_terms = ['month', 'เดือน']
    year_terms = ['year', 'ปี']
    quarter_terms = ['quarter', 'ไตรมาส', 'q']
    week_terms = ['week', 'สัปดาห์']
    day_terms = ['day', 'วัน']
    
    # Pattern 1: x_col is "month" and there's a "year" column → group by year
    if any(t in x_lower for t in month_terms):
        for col in df.columns:
            if any(t in col.lower() for t in year_terms):
                if df[col].nunique() > 1:
                    return col
    
    # Pattern 1b: x_col is "year" and there's a "month" column → group by year
    # This handles the case where recommend_chart selected year as x_col
    # We still want to group by year, but we need to swap x and series in the output
    if any(t in x_lower for t in year_terms):
        for col in df.columns:
            if any(t in col.lower() for t in month_terms):
                if df[col].nunique() > 1:
                    # Return the YEAR column (current x_col) as series
                    # But since x_col IS year, we need to signal a swap
                    # For now, return x_col itself to indicate the current x should become series
                    return x_col  # This signals: "year should be series, use month as x"
    
    # Pattern 2: x_col is "quarter" and there's a "year" column
    if any(t in x_lower for t in quarter_terms):
        for col in df.columns:
            if any(t in col.lower() for t in year_terms):
                if df[col].nunique() > 1:
                    return col
    
    # Pattern 3: x_col is "week" and there's a "year" column
    if any(t in x_lower for t in week_terms):
        for col in df.columns:
            if any(t in col.lower() for t in year_terms):
                if df[col].nunique() > 1:
                    return col
    
    # Pattern 4: x_col is "day" and there's a "month" column
    if any(t in x_lower for t in day_terms):
        for col in df.columns:
            if any(t in col.lower() for t in month_terms):
                if df[col].nunique() > 1:
                    return col
    
    # Pattern 5: Generic categorical grouper (e.g., product_line with month)
    time_keywords = ['month', 'quarter', 'week', 'day', 'date', 'เดือน', 'วัน']
    if any(t in x_lower for t in time_keywords):
        for col in df.columns:
            if col.lower() == x_lower or col == y_col:
                continue
            if df[col].nunique() >= 2 and df[col].nunique() <= 10:
                series_hints = ['line', 'category', 'type', 'group', 'status', 'region', 'country']
                if any(h in col.lower() for h in series_hints):
                    return col

    # Pattern 6: a low-cardinality grouping column that splits a categorical
    # axis (school_name x region, class x term) — the grouped/stacked bar case.
    # Time patterns above win, so a month axis keeps its year series.
    if len(df) >= 4 and df[x_col].nunique(dropna=True) >= 2:
        for col in df.columns:
            if col in (x_col, y_col) or col.lower().endswith('_id') or col.lower() == 'id':
                continue
            try:
                distinct = int(df[col].nunique(dropna=True))
            except TypeError:
                continue  # unhashable cells; never a grouping column
            if not 2 <= distinct <= 10:
                continue
            if pd.api.types.is_numeric_dtype(df[col]) and not any(
                h in col.lower() for h in _GROUPING_DIM_HINTS
            ):
                continue  # a second measure is not a series
            try:
                parts = df.groupby(x_col, dropna=True)[col].nunique(dropna=True)
            except (KeyError, TypeError, ValueError):
                continue
            if parts.empty or int(parts.min()) < 2:
                continue
            return col

    return None


def _repeating_label_cols(df: pd.DataFrame, label_cols: List[str]) -> set:
    """Label columns that would give several bars the same name (e.g. one
    source code on every row). They lose the axis to the best label column
    that does tell rows apart: unique per row first, else at least varying."""
    if len(df) < 2:
        return set()
    distinct = {}
    for c in label_cols:
        try:
            distinct[c] = int(df[c].nunique(dropna=False))
        except TypeError:
            distinct[c] = 0  # unhashable cells; never a good label
    for floor in (len(df), 2):
        if any(n >= floor for n in distinct.values()):
            return {c for c, n in distinct.items() if n < floor}
    return set()


# Chart-kind keys the service may name (ADR 0015). The envelope speaks keys and
# the rendering UI owns display labels, so a Consumer can dispatch on them and no
# option can be one the renderer does not implement. `table`/`none` are terminal.
CHART_KINDS = (
    "bar",
    "bar_horizontal",
    "bar_grouped",
    "bar_stacked",
    "bar_stacked_100",
    "line",
    "area",
    "combo",
    "pie",
    "scatter",
    "table",
    "none",
)

# How a series role should be drawn, when one exists.
SERIES_FORMS = ("grouped", "stacked", "stacked_100")

# The order the recommendation assumes; a Consumer may honour it or sort its own way.
SORT_ORDERS = ("value_desc", "x_asc", "row_order")

_SERIES_FORM_KIND = {
    "grouped": "bar_grouped",
    "stacked": "bar_stacked",
    "stacked_100": "bar_stacked_100",
}
_KIND_FORM = {kind: form for form, kind in _SERIES_FORM_KIND.items()}

# A category axis longer than this reads better horizontally (same value as the
# demo renderer's threshold).
_HORIZONTAL_BAR_THRESHOLD = 8

# Percent-like measures; `_column_info` already types most of these, these hints
# cover names it does not (share, ratio, Thai สัดส่วน).
_PERCENT_NAME_HINTS = ("share", "ratio", "สัดส่วน", "ร้อยละ")

# Axes whose values have an intrinsic order, where sorting by value would lie.
_ORDERED_AXIS_HINTS = (
    "date", "time", "year", "month", "quarter", "week", "day",
    "วันที่", "เดือน", "ปี", "ไตรมาส", "สัปดาห์",
)

# Numeric columns that name a grouping dimension rather than a measure.
_GROUPING_DIM_HINTS = (
    "year", "term", "round", "cohort", "group", "type", "category",
    "region", "phase", "ปี", "ภาค", "รอบ", "กลุ่ม", "ประเภท",
)


def _is_percent_measure(col: str, semantic_type: str) -> bool:
    return semantic_type == "percent" or any(
        hint in col.lower() for hint in _PERCENT_NAME_HINTS)


def combo_pair(num_cols: List[str], semantic: Dict[str, str]) -> Optional[Tuple[str, str]]:
    """`(bar_measure, line_measure)` when a result pairs a count-like measure
    with a rate/percent measure — the combo case (ADR 0015)."""
    percent = [c for c in num_cols if _is_percent_measure(c, semantic.get(c, "number"))]
    counts = [c for c in num_cols if semantic.get(c) == "count" and c not in percent]
    if percent and counts:
        return counts[0], percent[0]
    return None


def _partitions_a_total(df: pd.DataFrame, x_col: str, y_col: str, series_col: str) -> bool:
    """True when every x splits into several series values and those parts sum
    to the same total across x — the part-to-whole shape that stacks."""
    try:
        per_x = df.groupby(x_col)[y_col].sum()
        parts_per_x = df.groupby(x_col)[series_col].nunique()
    except (KeyError, TypeError, ValueError):
        return False
    if len(per_x) < 2 or int(parts_per_x.min()) < 2:
        return False
    totals = per_x.astype(float)
    if not bool((totals > 0).all()):
        return False
    return bool(totals.max() - totals.min() <= 0.01 * totals.max())


def series_form(df: pd.DataFrame, x_col: str, y_col: str, series_col: str,
                semantic: Optional[Dict[str, str]] = None) -> str:
    """Grouped vs stacked vs stacked-100%, by rules a test can pin:
    a percent measure already sums to 100 across the series; additive parts that
    share one total per x are a part-to-whole; anything else compares series."""
    sem = semantic or {c: _column_info(c, df[c])["semantic_type"] for c in df.columns}
    y_type = sem.get(y_col, "number")
    if _is_percent_measure(y_col, y_type):
        return "stacked_100"
    if y_type in ("count", "number") and _partitions_a_total(df, x_col, y_col, series_col):
        return "stacked"
    return "grouped"


def _is_ordered_axis(df: pd.DataFrame, x_col: Optional[str]) -> bool:
    """Dates, numeric axes and year/month-like names carry their own order."""
    if not x_col or x_col not in df.columns:
        return False
    if _column_info(x_col, df[x_col])["semantic_type"] == "date":
        return True
    if pd.api.types.is_numeric_dtype(df[x_col]):
        return True
    return any(hint in x_col.lower() for hint in _ORDERED_AXIS_HINTS)


def sort_for(chart_type: str, df: pd.DataFrame, x_col: Optional[str]) -> Optional[str]:
    """The ordering the recommendation assumes for this kind."""
    if not x_col or x_col not in df.columns:
        return None
    if chart_type in ("bar", "bar_horizontal", "pie"):
        return "value_desc"
    if chart_type == "combo":
        return "x_asc" if _is_ordered_axis(df, x_col) else "value_desc"
    if chart_type in ("line", "area"):
        return "x_asc" if _is_ordered_axis(df, x_col) else "row_order"
    if chart_type in _KIND_FORM:
        return "x_asc" if _is_ordered_axis(df, x_col) else "row_order"
    return None


def chart_options(
    df: pd.DataFrame,
    chart_type: str,
    x_col: Optional[str] = None,
    y_col: Optional[str] = None,
    series_col: Optional[str] = None,
) -> List[str]:
    """The chart kinds this result can actually be drawn as (ADR 0015).

    Derived from the grid — a label axis, the measures present, whether a series
    role exists — instead of a static per-type list, so an offered kind always
    has the data it needs and every key is one the renderer implements.
    """
    semantic = {c: _column_info(c, df[c])["semantic_type"] for c in df.columns}
    numeric = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c]) and semantic[c] != "id"
    ]
    has_label = bool(x_col and x_col in df.columns
                     and semantic.get(x_col) in ("name", "category", "text"))
    has_measure = bool(y_col and y_col in numeric)

    options: List[str] = []
    if has_label and has_measure:
        options += ["bar", "bar_horizontal", "line", "area"]
        if not series_col:
            options.append("pie")
        if series_col and series_col in df.columns and df[series_col].nunique(dropna=True) > 1:
            options += ["bar_grouped", "bar_stacked", "bar_stacked_100"]
        if not series_col and combo_pair(numeric, semantic):
            options.append("combo")
    if len(numeric) >= 2 and len(df) >= 2:
        options.append("scatter")
    options.append("table")

    # The recommended kind is always offered, even when the grid is thin.
    if chart_type in CHART_KINDS and chart_type not in ("none", "table") \
            and chart_type not in options:
        options.insert(0, chart_type)
    return options


def recommend_chart(df: pd.DataFrame, question: str = "", preferred_chart_type: str = None) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Analyze dataframe and recommend (chart_type, x_col, y_col).
    Chart types: 'bar', 'line', 'area', 'scatter', 'pie', 'table'
    
    Priority:
    1. preferred_chart_type (user selected from dropdown)
    2. Keywords in question text
    3. Auto-detection based on data structure
    """
    if df.empty:
        return "none", None, None

    # Semantic types per ADR 0004 — the axis policy's source of truth.
    semantic = {c: _column_info(c, df[c])["semantic_type"] for c in df.columns}

    # ADR 0008: ids never label an axis. Keep the legacy keyword heuristics for
    # chart-type/time detection, but drop id columns from every candidate queue.
    id_cols = {c for c, s in semantic.items() if s == "id"}
    _LABEL_PRIORITY = {"name": 0, "category": 1, "text": 2}
    axis_label_cols = sorted(
        (c for c in df.columns if semantic[c] in _LABEL_PRIORITY),
        key=lambda c: _LABEL_PRIORITY[semantic[c]],
    )
    repeating_cols = _repeating_label_cols(df, axis_label_cols)
    axis_label_cols = [c for c in axis_label_cols if c not in repeating_cols]

    def _axis_pick(current: Optional[str]) -> Optional[str]:
        """Upgrade an axis pick to the policy's best label column, if any."""
        if not axis_label_cols:
            return current
        if current is None or current in id_cols or current in repeating_cols:
            return axis_label_cols[0]
        if current in axis_label_cols and current != axis_label_cols[0]:
            return axis_label_cols[0]
        return current

    # Identify column types
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    object_cols = df.select_dtypes(include=['object', 'category', 'datetime']).columns.tolist()

    # Helper to identify column roles
    def is_time_col(col: str) -> bool:
        terms = ['date', 'time', 'year', 'month', 'day', 'hour', 'minute', 'second', 'quarter', 'week', 'id', 'no', 'number', 'code']
        return any(t in col.lower() for t in terms)

    def is_metric_col(col: str) -> bool:
        terms = ['count', 'sum', 'total', 'avg', 'min', 'max', 'amount', 'price', 'quantity', 'value', 'score', 'rate', 'percent', 'sales', 'revenue', 'profit', 'cost']
        return any(t in col.lower() for t in terms)

    # Sort numeric columns: Metrics first, Time/ID last
    numeric_cols.sort(key=lambda c: (not is_metric_col(c), is_time_col(c)))

    # Identify potential Date/Category columns from numeric too (e.g. Year, Month as int)
    # Move likely dimensions (Year/Month) from numeric_cols to object_cols for X-axis consideration
    # IF they are NOT the only numeric column
    if len(numeric_cols) >= 2:
        dims = [c for c in numeric_cols if is_time_col(c) and not is_metric_col(c)]
        for d in dims:
            if len(numeric_cols) > 1: # Keep at least one numeric for Y-axis
                numeric_cols.remove(d)
                object_cols.insert(0, d) # Treat as dimension

    # Non-id numeric candidates for the value axis (ADR 0008).
    num_axis = [c for c in numeric_cols if c not in id_cols]
    # A value repeated on every row (a total, a slice-wide count) draws equal
    # bars; plot a column that varies first.
    flat_values = {c for c in num_axis if len(df) > 1 and df[c].nunique(dropna=False) <= 1}
    if len(flat_values) < len(num_axis):
        num_axis.sort(key=lambda c: c in flat_values)

    # Priority 1: User preference from dropdown (highest priority) — but the
    # axis policy still rules: a preferred type with no label column falls
    # through to auto, which yields a table under the policy.
    if preferred_chart_type and preferred_chart_type != 'auto':
        pref = preferred_chart_type
        bar_like = ("bar", "bar_horizontal", "bar_grouped", "bar_stacked", "bar_stacked_100")
        if pref == 'pie' and axis_label_cols and num_axis:
            return "pie", axis_label_cols[0], num_axis[0]
        elif pref == 'scatter':
            if len(num_axis) >= 2:
                return "scatter", num_axis[0], num_axis[1]
            elif axis_label_cols and num_axis:
                return "scatter", axis_label_cols[0], num_axis[0]
        elif pref in ('line', 'area') and axis_label_cols and num_axis:
            return pref, axis_label_cols[0], num_axis[0]
        elif pref == 'combo':
            pair = combo_pair(num_axis, semantic)
            if pair and axis_label_cols:
                return "combo", axis_label_cols[0], pair[0]
        elif pref in bar_like and axis_label_cols and num_axis:
            return pref, axis_label_cols[0], num_axis[0]

    # Priority 2: User Preference from question keywords
    q = question.lower()
    user_pref = None
    
    # Pie chart keywords
    pie_keywords = ['pie', 'วงกลม', 'สัดส่วน', 'เปอร์เซ็นต์', 'percent', 'proportion', 
                    'ส่วนแบ่ง', 'องค์ประกอบ', 'แบ่งสัดส่วน', 'composition']
    
    # Bar chart keywords
    bar_keywords = ['bar', 'แท่ง', 'เปรียบเทียบ', 'compare', 'comparison', 'ranking', 
                    'อันดับ', 'จัดอันดับ', 'top', 'สูงสุด', 'ต่ำสุด', 'มากที่สุด', 'น้อยที่สุด']
    
    # Line chart keywords  
    line_keywords = ['line', 'trend', 'เส้น', 'แนวโน้ม', 'ช่วงเวลา', 'timeline', 
                     'ตามเดือน', 'ตามปี', 'รายวัน', 'รายเดือน', 'รายปี', 'การเปลี่ยนแปลง',
                     'growth', 'เติบโต', 'time series', 'ประวัติ', 'history']
    
    # Scatter chart keywords
    scatter_keywords = ['scatter', 'จุด', 'กระจาย', 'correlation', 'ความสัมพันธ์', 
                        'relationship', 'distribution', 'การกระจาย', 'plot']
    
    if any(kw in q for kw in pie_keywords):
        user_pref = 'pie'
    elif any(kw in q for kw in line_keywords):
        user_pref = 'line'
    elif any(kw in q for kw in scatter_keywords):
        user_pref = 'scatter'
    elif any(kw in q for kw in bar_keywords):
        user_pref = 'bar'
    
    # Apply keyword preference (axis policy still applies — ADR 0008)
    if user_pref == 'pie' and axis_label_cols and num_axis:
        return "pie", axis_label_cols[0], num_axis[0]
    elif user_pref == 'line' and axis_label_cols and num_axis:
        return "line", axis_label_cols[0], num_axis[0]
    elif user_pref == 'scatter':
        if len(num_axis) >= 2:
            return "scatter", num_axis[0], num_axis[1]
        elif axis_label_cols and num_axis:
            return "scatter", axis_label_cols[0], num_axis[0]
    elif user_pref == 'bar' and axis_label_cols and num_axis:
        return "bar", axis_label_cols[0], num_axis[0]
        
    # Case 1: Time Series (Date/Month + Numeric) -> Line
    # Check if any object col looks like a date/month
    time_keywords = ['date', 'time', 'month', 'year', 'day', 'quarter', 'week', 'วันที่', 'เดือน', 'ปี']
    date_col = None
    for col in object_cols:
        if col in id_cols:
            continue
        if any(k in col.lower() for k in time_keywords):
            date_col = col
            break
            
    if date_col and numeric_cols:
        return "line", date_col, numeric_cols[0]
        
    # Case 2: Ranking / Comparison (Label + Numeric) -> bar family. A count-like
    # measure beside a rate/percent one is the combo case; a long category axis
    # reads horizontally.
    cat_col = _axis_pick(object_cols[0]) if object_cols else None
    if cat_col and cat_col not in id_cols and num_axis:
        pair = combo_pair(num_axis, semantic)
        if pair:
            return "combo", cat_col, pair[0]
        try:
            distinct = int(df[cat_col].nunique(dropna=True))
        except TypeError:
            distinct = 0
        kind = "bar_horizontal" if distinct > _HORIZONTAL_BAR_THRESHOLD else "bar"
        return kind, cat_col, num_axis[0]

    # Case 3: Correlation (2 non-id Numeric cols) -> Scatter. One row is one
    # point, not a correlation: fall through to a table.
    if len(num_axis) >= 2 and len(df) >= 2:
        return "scatter", num_axis[0], num_axis[1]

    # Case 4: no axis label column under the policy -> not chartable (ADR 0008)
    return "table", None, None

_CHART_REASON_TH = {
    "bar": "เทียบค่าข้ามหมวดหมู่",
    "bar_horizontal": "เทียบค่าข้ามหมวดหมู่มาก ๆ — แนวนอนอ่านชื่อได้เต็ม",
    "bar_grouped": "เปรียบเทียบแต่ละหมวดย่อยในกลุ่มเดียวกัน",
    "bar_stacked": "ดูว่าองค์ประกอบต่าง ๆ รวมกันเป็นยอดของแต่ละหมวดอย่างไร",
    "bar_stacked_100": "ดูสัดส่วนองค์ประกอบภายในแต่ละหมวด (รวมเป็น 100%)",
    "combo": "ดูจำนวนและอัตราไปพร้อมกัน",
    "line": "ดูแนวโน้มตามลำดับเวลา",
    "area": "ดูแนวโน้มและขนาดที่สะสมตามลำดับเวลา",
    "pie": "ดูสัดส่วนขององค์ประกอบ",
    "scatter": "ดูความสัมพันธ์ระหว่างสองตัวแปร",
    "table": "ข้อมูลไม่เหมาะกับกราฟ แสดงเป็นตาราง",
    "none": "ไม่มีข้อมูลให้แสดง",
}

# Fold a category axis into a "top N + other" view past this many distinct values.
_TOP_N_THRESHOLD = 12


def humanize_label(col: Optional[str]) -> Optional[str]:
    """`attendance_rate_percent` -> `attendance rate percent`. Thai names pass through."""
    if not col:
        return None
    return col.replace("_", " ").strip()


def compute_top_n(df: pd.DataFrame, chart_type: str, x_col: Optional[str]) -> Optional[int]:
    if chart_type not in ("bar", "bar_horizontal", "pie") or not x_col or x_col not in df.columns:
        return None
    try:
        distinct = int(df[x_col].nunique(dropna=True))
    except TypeError:
        return None  # unhashable cells; no meaningful category count
    return _TOP_N_THRESHOLD if distinct > _TOP_N_THRESHOLD else None


def _series_role(df: pd.DataFrame, x_col: str, y_col: str):
    """(x, series) for a multi-series result, swapping a year-as-x pick for the
    month column so the year becomes the series."""
    series_col = detect_series_column(df, x_col, y_col)
    if series_col and series_col == x_col:
        for col in df.columns:
            if col == x_col or col == y_col:
                continue
            if any(t in col.lower() for t in ("month", "เดือน")):
                return col, series_col
    return x_col, series_col


def plan_chart(df: pd.DataFrame, question: str = "",
               preferred_chart_type: str = None) -> Dict[str, Any]:
    """One place that decides a result's chart plan (ADR 0015).

    Returns the chart-kind key, the axis columns, the series role, the combo's
    second measure, the intended series form and the sort the recommendation
    assumes. `VizService.recommend` turns this into the envelope's config.
    """
    chart_type, x_col, y_col = recommend_chart(df, question, preferred_chart_type)
    semantic = {c: _column_info(c, df[c])["semantic_type"] for c in df.columns}
    plan = {
        "chart_type": chart_type,
        "x_col": x_col,
        "y_col": y_col,
        "series_col": None,
        "y2_col": None,
        "chart_form": None,
        "sort": None,
    }

    drawable = bool(x_col and y_col and x_col in df.columns and y_col in df.columns)
    cartesian = ("bar", "bar_horizontal", "line", "area", "combo") + tuple(_KIND_FORM)

    if chart_type == "combo" and drawable:
        numeric = [c for c in df.columns
                   if pd.api.types.is_numeric_dtype(df[c]) and semantic[c] != "id"]
        pair = combo_pair(numeric, semantic)
        if pair:
            plan["y_col"], plan["y2_col"] = pair
        else:
            plan["chart_type"] = "bar"   # nothing to put on the second axis
    elif chart_type in cartesian and drawable:
        x_col, series_col = _series_role(df, x_col, y_col)
        plan["x_col"], plan["series_col"] = x_col, series_col

        if chart_type in _KIND_FORM:
            # An explicit series form is honoured when the result has a series
            # role; without one it degrades to the plain bar it can draw.
            if series_col:
                plan["chart_form"] = _KIND_FORM[chart_type]
            else:
                plan["chart_type"] = "bar"
        elif chart_type in ("bar", "bar_horizontal") and series_col:
            form = series_form(df, x_col, y_col, series_col, semantic)
            plan["chart_form"] = form
            plan["chart_type"] = _SERIES_FORM_KIND[form]

    plan["sort"] = sort_for(plan["chart_type"], df, plan["x_col"])
    return plan


def recommend_chart_with_series(
    df: pd.DataFrame, question: str = "", preferred_chart_type: str = None
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """Compatibility wrapper: the legacy (chart_type, x, y, series) tuple."""
    plan = plan_chart(df, question, preferred_chart_type)
    return plan["chart_type"], plan["x_col"], plan["y_col"], plan["series_col"]


_NO_LABEL_REASON = "ไม่มีคอลัมน์ชื่อสำหรับเป็นแกน — แสดงเป็นตารางแทน (ลองถามให้แสดงชื่อมาด้วย)"


def _table_config(config: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """A table is the honest fallback; every chart-only role is cleared."""
    return {
        "chart_type": "table",
        "x_col": None,
        "y_col": None,
        "series_col": None,
        "y2_col": None,
        "chart_form": None,
        "sort": None,
        "options": ["table"],
        "title": config.get("title") or "ผลลัพธ์",
        "x_label": None,
        "y_label": None,
        "top_n": None,
        "reason": reason,
    }


def _enforce_axis_policy(config: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    """ADR 0008 exit guard, extended by ADR 0015: whatever recommended the
    config, an id never labels an axis, a result without an axis label column
    is not chartable, and the kind must be one the renderer can draw with the
    roles this result actually has. The alternatives are recomputed last, so
    they only ever offer kinds that survived."""
    chart_type = config.get("chart_type")
    if chart_type == "table":
        return _table_config(config, config.get("reason") or _CHART_REASON_TH["table"])
    if chart_type in (None, "none"):
        return config

    semantic = {c: _column_info(c, df[c])["semantic_type"] for c in df.columns}
    id_cols = {c for c, s in semantic.items() if s == "id"}
    label_cols = [
        c for c in df.columns
        if semantic[c] in ("name", "category", "text")
    ]
    repeating_cols = _repeating_label_cols(df, label_cols)
    label_cols = [c for c in label_cols if c not in repeating_cols]

    def _fix(col: Optional[str]) -> Optional[str]:
        if col not in id_cols and col not in repeating_cols:
            return col
        return label_cols[0] if label_cols else None

    x_col = _fix(config.get("x_col"))
    y_col = config.get("y_col")
    if not x_col or not y_col or y_col in id_cols or y_col not in df.columns:
        return _table_config(config, _NO_LABEL_REASON)

    if x_col != config.get("x_col") or y_col != config.get("y_col"):
        config["x_col"] = x_col
        config["y_col"] = y_col
        config["x_label"] = humanize_label(x_col)
        config["y_label"] = humanize_label(y_col)
        config["reason"] = _CHART_REASON_TH.get(chart_type, config.get("reason", ""))

    series_col = config.get("series_col")
    if series_col not in df.columns:
        series_col = None

    # Renderability (ADR 0015): a series form without a series role, or a combo
    # without its second measure, cannot be drawn — degrade to the plain bar.
    if chart_type in _KIND_FORM and (
        not series_col or int(df[series_col].nunique(dropna=True)) < 2
    ):
        chart_type = "bar"
    if chart_type == "combo" and config.get("y2_col") not in df.columns:
        chart_type = "bar"
    if chart_type not in CHART_KINDS:
        chart_type = "table"
    if chart_type == "table":
        return _table_config(config, _CHART_REASON_TH["table"])

    config["chart_type"] = chart_type
    config["series_col"] = series_col
    config["y2_col"] = config.get("y2_col") if chart_type == "combo" else None
    if chart_type in _KIND_FORM:
        config["chart_form"] = _KIND_FORM[chart_type]
    elif series_col and chart_type in ("bar", "bar_horizontal"):
        form = config.get("chart_form")
        config["chart_form"] = (
            form if form in SERIES_FORMS
            else series_form(df, x_col, y_col, series_col, semantic)
        )
    else:
        # A form is a bar concept; a multi-series line states none.
        config["chart_form"] = None
    if config.get("sort") not in SORT_ORDERS:
        config["sort"] = sort_for(chart_type, df, x_col)
    config["top_n"] = compute_top_n(df, chart_type, x_col)
    config["options"] = chart_options(df, chart_type, x_col, y_col, series_col)
    return config


class VizService:
    """
    Unified visualization recommendation service.

    Encapsulates both rule-based and AI-powered visualization logic,
    providing a single entry point for engine.py to use.
    """

    def __init__(self, llm=None, enable_intelligent: bool = False):
        """
        Initialize VizService.

        Args:
            llm: Optional LangChain LLM for intelligent recommendations.
            enable_intelligent: Whether to use AI-powered recommendations.
        """
        self._llm = llm
        self._enable_intelligent = enable_intelligent

    def recommend(
        self,
        df: pd.DataFrame,
        question: str = "",
        preferred_chart_type: str = None
    ) -> Dict[str, Any]:
        """
        Get visualization recommendation for the given data.

        Uses intelligent (AI) recommendation if enabled and available,
        otherwise falls back to rule-based recommendation.

        Args:
            df: DataFrame containing query results.
            question: User's original question.
            preferred_chart_type: Optional user-selected chart type.

        Returns:
            Dict with chart_type, x_col, y_col, series_col, options, title, reason.
        """
        if df is None or df.empty:
            return {
                "chart_type": "none",
                "x_col": None,
                "y_col": None,
                "series_col": None,
                "y2_col": None,
                "chart_form": None,
                "sort": None,
                "options": ["table"],
                "title": "No Data",
                "reason": "Empty result set"
            }

        # Try intelligent recommendation first
        if self._llm and self._enable_intelligent:
            try:
                viz_config = recommend_chart_intelligent(df, question, self._llm)
                # The AI picks a kind and axes; roles it cannot know stay empty.
                viz_config["series_col"] = None
                viz_config["y2_col"] = None
                viz_config["chart_form"] = None
                viz_config["sort"] = None
                viz_config["options"] = chart_options(
                    df, viz_config.get("chart_type", "table"),
                    viz_config.get("x_col"), viz_config.get("y_col"))
                return _enforce_axis_policy(viz_config, df)
            except Exception:
                pass  # Fall through to rule-based

        # Fallback to rule-based
        plan = plan_chart(df, question, preferred_chart_type)
        chart_type = plan["chart_type"]
        x_col, y_col = plan["x_col"], plan["y_col"]
        series_col = plan["series_col"]

        x_label = humanize_label(x_col)
        y_label = humanize_label(y_col)
        title = (question or "").strip() or (
            f"{y_label} ตาม {x_label}" if x_label and y_label else "ผลลัพธ์"
        )

        reason = _CHART_REASON_TH.get(chart_type, "")
        if chart_type == "table" and x_col is None:
            _has_label = any(
                _column_info(c, df[c])["semantic_type"] in ("name", "category", "text")
                for c in df.columns
            )
            if not _has_label:
                reason = _NO_LABEL_REASON

        config = {
            "chart_type": chart_type,
            "x_col": x_col,
            "y_col": y_col,
            "series_col": series_col,
            "y2_col": plan["y2_col"],
            "chart_form": plan["chart_form"],
            "sort": plan["sort"],
            "options": chart_options(df, chart_type, x_col, y_col, series_col),
            "title": title,
            "x_label": x_label,
            "y_label": y_label,
            "top_n": compute_top_n(df, chart_type, x_col),
            "reason": reason,
        }
        return _enforce_axis_policy(config, df)


def create_viz_service(llm=None, enable_intelligent: bool = False) -> VizService:
    """Factory function to create VizService instance."""
    return VizService(llm=llm, enable_intelligent=enable_intelligent)


def recommend_chart_intelligent(df: pd.DataFrame, question: str, llm) -> Dict[str, Any]:
    """
    Use AI to analyze dataframe and question to suggest best visualization in JSON.
    Returns:
        {
            "chart_type": "bar" | "line" | "pie" | "scatter" | "table",
            "x_col": str,
            "y_col": str,
            "title": str,
            "reason": str
        }
    """
    if df.empty:
        return {"chart_type": "table", "title": "No Data"}

    # Prepare data sample (first row + columns) to save tokens
    columns = list(df.columns)
    sample_data = df.iloc[0].to_dict() if not df.empty else {}
    
    parser = JsonOutputParser()
    
    prompt = PromptTemplate(
        template="""
        Analyze the user query and the returned data sample to suggest the best visualization.
        
        User Query: "{question}"
        Data Columns: {columns}
        First Row Data: {sample_data}
        
        Return a JSON object with these keys:
        - "chart_type": One of ["bar", "bar_horizontal", "line", "area", "pie", "scatter", "table"].
        - "title": A concise title for the chart (in Thai if query is Thai).
        - "x_col": Column name for X-axis (labels).
        - "y_col": Column name for Y-axis (values).
        - "reason": Why you chose this chart.
        
        {format_instructions}
        """,
        input_variables=["question", "columns", "sample_data"],
        partial_variables={"format_instructions": parser.get_format_instructions()}
    )
    
    chain = prompt | llm | parser
    
    try:
        config = chain.invoke({
            "question": question,
            "columns": str(columns),
            "sample_data": str(sample_data)
        })
        
        # Fallback validation
        if not config.get("chart_type"):
            config["chart_type"] = "table"
            
        return config
        
    except Exception as e:
        print(f"⚠️ Viz AI Success Failed: {e}. Falling back to rule-based.")
        # Fallback to rule-based
        c_type, x, y = recommend_chart(df, question)
        return {
            "chart_type": c_type,
            "x_col": x,
            "y_col": y,
            "title": "Visualization",
            "reason": "Fallback to rule-based due to AI error"
        }

