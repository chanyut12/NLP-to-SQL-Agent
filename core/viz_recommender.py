"""
Visualization Recommender System.
Analyzes DataFrame content to suggest the best chart type.
"""
import pandas as pd
from typing import Tuple, Optional, List

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

