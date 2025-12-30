"""
Simple evaluation script to measure agent performance against a golden dataset.
Note: Requires running app/db context or mocking the engine.
For simplicity, this script focuses on SQL syntax validity and execution success 
against the local mock DB (SQLite).
"""

import sys
import os
import json
import pandas as pd
from sqlalchemy import create_engine
import time

# Add parent dir to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import core logic (assuming we can refactor app.py or import from it)
# Since app.py has streamlit calls at module level, importing it might trigger UI.
# In a real refactor, we should move logic to 'agent.py'. 
# For now, we mock the execution or rely on a separate test runner.

def run_eval(dataset_path, db_path="../local_database.db"):
    print(f"Loading dataset: {dataset_path}")
    with open(dataset_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Setup Engine
    engine = create_engine(f"sqlite:///{db_path}")
    
    results = []
    
    print(f"Running evaluation on {len(data['examples'])} examples...")
    
    for ex in data['examples']:
        question = ex['question']
        gold_sql = ex['sql']
        
        # Here we would call the agent. 
        # Since we can't easily import 'generate_sql_with_retry' without refactoring app.py completely 
        # (due to st.session_state deps), we will simulate a "Execution Check" of the GOLD SQL only.
        # This verifies that our golden dataset is at least valid.
        
        start = time.time()
        success = False
        error = None
        rows = 0
        
        try:
            df = pd.read_sql(gold_sql, engine)
            success = True
            rows = len(df)
        except Exception as e:
            error = str(e)
            
        duration = time.time() - start
        
        results.append({
            "question": question,
            "success": success,
            "rows": rows,
            "error": error,
            "duration": duration
        })
        
    # Metrics
    df_res = pd.DataFrame(results)
    print("\n--- Evaluation Results (Golden SQL Validity) ---")
    print(f"Total: {len(df_res)}")
    print(f"Success Rate: {df_res['success'].mean():.2%}")
    print(f"Avg Duration: {df_res['duration'].mean():.4f}s")
    
    if not df_res[~df_res['success']].empty:
        print("\nFailed Queries:")
        print(df_res[~df_res['success']][['question', 'error']])

if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_eval(sys.argv[1])
    else:
        print("Usage: python run_eval.py <dataset.json>")

