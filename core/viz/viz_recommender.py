"""
Visualization Recommender System.
Analyzes DataFrame content to suggest the best chart type.
"""
import pandas as pd
from typing import Tuple, Optional, List, Dict, Any
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

    # Priority 1: User preference from dropdown (highest priority)
    if preferred_chart_type and preferred_chart_type != 'auto':
        if preferred_chart_type == 'pie' and object_cols and numeric_cols:
            return "pie", object_cols[0], numeric_cols[0]
        elif preferred_chart_type == 'scatter':
            if len(numeric_cols) >= 2:
                return "scatter", numeric_cols[0], numeric_cols[1]
            elif object_cols and numeric_cols:
                return "scatter", object_cols[0], numeric_cols[0]
        elif preferred_chart_type == 'line' and object_cols and numeric_cols:
            return "line", object_cols[0], numeric_cols[0]
        elif preferred_chart_type == 'bar' and object_cols and numeric_cols:
            return "bar", object_cols[0], numeric_cols[0]

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
    
    # Apply keyword preference
    if user_pref == 'pie' and object_cols and numeric_cols:
        return "pie", object_cols[0], numeric_cols[0]
    elif user_pref == 'line' and object_cols and numeric_cols:
        return "line", object_cols[0], numeric_cols[0]
    elif user_pref == 'scatter':
        if len(numeric_cols) >= 2:
            return "scatter", numeric_cols[0], numeric_cols[1]
        elif object_cols and numeric_cols:
            return "scatter", object_cols[0], numeric_cols[0]
    elif user_pref == 'bar' and object_cols and numeric_cols:
        return "bar", object_cols[0], numeric_cols[0]
        
    # Case 1: Time Series (Date/Month + Numeric) -> Line
    # Check if any object col looks like a date/month
    time_keywords = ['date', 'time', 'month', 'year', 'day', 'quarter', 'week', 'วันที่', 'เดือน', 'ปี']
    date_col = None
    for col in object_cols:
        if any(k in col.lower() for k in time_keywords):
            date_col = col
            break
            
    if date_col and numeric_cols:
        return "line", date_col, numeric_cols[0]
        
    # Case 2: Ranking / Comparison (Category + Numeric) -> Bar
    if object_cols and numeric_cols:
        cat_col = object_cols[0] # Assume first categorical is the main grouping
        val_col = numeric_cols[0] # First numeric is likely the metric (sorted above)
        
        # If too many categories, maybe bar is crowded, but usually bar is best for ranking
        return "bar", cat_col, val_col
        
    # Case 3: Correlation (2 Numeric cols) -> Scatter
    if len(numeric_cols) >= 2:
        return "scatter", numeric_cols[0], numeric_cols[1]
        
    # Case 4: Single Value or just Table
    return "table", None, None

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
                return viz_config
            except Exception:
                pass  # Fall through to rule-based

        # Fallback to rule-based
        chart_type, x_col, y_col, series_col = recommend_chart_with_series(
            df, question, preferred_chart_type
        )

        return {
            "chart_type": chart_type,
            "x_col": x_col,
            "y_col": y_col,
            "series_col": series_col,
            "options": get_chart_options(chart_type),
            "title": "Visualization",
            "reason": "Rule-based recommendation"
        }


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

