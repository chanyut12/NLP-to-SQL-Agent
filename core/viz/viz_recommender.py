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
        if preferred_chart_type == 'pie' and axis_label_cols and num_axis:
            return "pie", axis_label_cols[0], num_axis[0]
        elif preferred_chart_type == 'scatter':
            if len(num_axis) >= 2:
                return "scatter", num_axis[0], num_axis[1]
            elif axis_label_cols and num_axis:
                return "scatter", axis_label_cols[0], num_axis[0]
        elif preferred_chart_type == 'line' and axis_label_cols and num_axis:
            return "line", axis_label_cols[0], num_axis[0]
        elif preferred_chart_type == 'bar' and axis_label_cols and num_axis:
            return "bar", axis_label_cols[0], num_axis[0]

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
        
    # Case 2: Ranking / Comparison (Label + Numeric) -> Bar
    cat_col = _axis_pick(object_cols[0]) if object_cols else None
    if cat_col and cat_col not in id_cols and num_axis:
        return "bar", cat_col, num_axis[0]

    # Case 3: Correlation (2 non-id Numeric cols) -> Scatter. One row is one
    # point, not a correlation: fall through to a table.
    if len(num_axis) >= 2 and len(df) >= 2:
        return "scatter", num_axis[0], num_axis[1]

    # Case 4: no axis label column under the policy -> not chartable (ADR 0008)
    return "table", None, None

_CHART_REASON_TH = {
    "bar": "เทียบค่าข้ามหมวดหมู่",
    "line": "ดูแนวโน้มตามลำดับเวลา",
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
    if chart_type not in ("bar", "pie") or not x_col or x_col not in df.columns:
        return None
    try:
        distinct = int(df[x_col].nunique(dropna=True))
    except TypeError:
        return None  # unhashable cells; no meaningful category count
    return _TOP_N_THRESHOLD if distinct > _TOP_N_THRESHOLD else None


def get_chart_options(chart_type: str) -> List[str]:
    """Get compatible alternatives based on recommended type."""
    common = ["Table"]
    if chart_type in ["bar", "line", "area", "pie"]:
        return ["Bar Chart", "Line Chart", "Area Chart", "Pie Chart"] + common
    elif chart_type == "scatter":
        return ["Scatter Plot", "Bar Chart"] + common
    return common


def recommend_chart_with_series(
    df: pd.DataFrame, 
    question: str = "", 
    preferred_chart_type: str = None
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Enhanced version of recommend_chart that also detects multi-series patterns.
    
    Returns: (chart_type, x_col, y_col, series_col)
    - series_col: Column to use for splitting data into multiple series (e.g., 'year')
                  None if single-series chart.
    """
    # Get base recommendation
    chart_type, x_col, y_col = recommend_chart(df, question, preferred_chart_type)
    
    # Detect series column (only for line and bar charts)
    series_col = None
    if chart_type in ['line', 'bar'] and x_col and y_col:
        series_col = detect_series_column(df, x_col, y_col)
        
        # Handle swap case: if series_col == x_col, we need to find the actual x_col
        # This happens when detect_series_column returns x_col itself as a signal to swap
        if series_col and series_col == x_col:
            # Find the month column to use as new x_col
            month_terms = ['month', 'เดือน']
            for col in df.columns:
                if col != x_col and col != y_col:
                    if any(t in col.lower() for t in month_terms):
                        # Swap: month becomes x, year (original x) becomes series
                        x_col = col
                        break
    
    return chart_type, x_col, y_col, series_col


_NO_LABEL_REASON = "ไม่มีคอลัมน์ชื่อสำหรับเป็นแกน — แสดงเป็นตารางแทน (ลองถามให้แสดงชื่อมาด้วย)"


def _enforce_axis_policy(config: Dict[str, Any], df: pd.DataFrame) -> Dict[str, Any]:
    """ADR 0008 exit guard: whatever recommended the config, an id never labels
    an axis, and a result without an axis label column is not chartable."""
    chart_type = config.get("chart_type")
    if chart_type in (None, "none", "table"):
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
    if not x_col or not y_col or y_col in id_cols:
        return {
            "chart_type": "table",
            "x_col": None,
            "y_col": None,
            "series_col": None,
            "options": get_chart_options("table"),
            "title": config.get("title") or "ผลลัพธ์",
            "x_label": None,
            "y_label": None,
            "top_n": None,
            "reason": _NO_LABEL_REASON,
        }
    if x_col != config.get("x_col") or y_col != config.get("y_col"):
        config["x_col"] = x_col
        config["y_col"] = y_col
        config["x_label"] = humanize_label(x_col)
        config["y_label"] = humanize_label(y_col)
        config["reason"] = _CHART_REASON_TH.get(chart_type, config.get("reason", ""))
    config["top_n"] = compute_top_n(df, chart_type, x_col)
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
                "options": ["Table"],
                "title": "No Data",
                "reason": "Empty result set"
            }

        # Try intelligent recommendation first
        if self._llm and self._enable_intelligent:
            try:
                viz_config = recommend_chart_intelligent(df, question, self._llm)
                viz_config["options"] = get_chart_options(viz_config.get("chart_type", "table"))
                viz_config["series_col"] = None  # AI doesn't detect series yet
                return _enforce_axis_policy(viz_config, df)
            except Exception:
                pass  # Fall through to rule-based

        # Fallback to rule-based
        chart_type, x_col, y_col, series_col = recommend_chart_with_series(
            df, question, preferred_chart_type
        )

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
            "options": get_chart_options(chart_type),
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
        - "chart_type": One of ["bar", "line", "pie", "doughnut", "scatter", "table"].
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

