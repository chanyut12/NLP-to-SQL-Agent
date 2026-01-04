"""
Visualization Recommender System.
Analyzes DataFrame content to suggest the best chart type.
"""
import pandas as pd
from typing import Tuple, Optional, List

def recommend_chart(df: pd.DataFrame, question: str = "") -> Tuple[str, Optional[str], Optional[str]]:
    """
    Analyze dataframe and recommend (chart_type, x_col, y_col).
    Chart types: 'bar', 'line', 'area', 'scatter', 'pie', 'table'
    """
    if df.empty:
        return "none", None, None
        
    # Identify column types
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    object_cols = df.select_dtypes(include=['object', 'category', 'datetime']).columns.tolist()

    # User Preference Override
    q = question.lower()
    user_pref = None
    if 'pie' in q or 'วงกลม' in q:
        user_pref = 'pie'
    elif 'bar' in q or 'แท่ง' in q:
        user_pref = 'bar'
    elif 'line' in q or 'trend' in q or 'เส้น' in q or 'แนวโน้ม' in q:
        user_pref = 'line'
    elif 'scatter' in q or 'จุด' in q or 'กระจาย' in q:
        user_pref = 'scatter'
        
    if user_pref == 'pie' and object_cols and numeric_cols:
        return "pie", object_cols[0], numeric_cols[0]
        
    # Case 1: Time Series (Date/Month + Numeric) -> Line/Area
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
        val_col = numeric_cols[0]
        
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

