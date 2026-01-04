import sqlite3
import sqlglot
import os

def convert_mysql_to_sqlite(mysql_file, sqlite_file):
    print(f"Converting {mysql_file} to {sqlite_file} using sqlglot...")
    
    if os.path.exists(sqlite_file):
        os.remove(sqlite_file)
        
    conn = sqlite3.connect(sqlite_file)
    cursor = conn.cursor()
    
    with open(mysql_file, 'r', encoding='utf-8', errors='ignore') as f:
        # Read line by line to handle large files, but for now strict readall is fine defined size
        sql_content = f.read()

    # Pre-clean known non-standard MySQL dump artifacts that sqlglot might choke on hard
    # Remove weird comments or set commands
    sql_content = sql_content.replace(r"\'", "''") # Basic escape fix for text content
    
    # Split queries manually or let sqlglot handle it? 
    # transpile returns a list of strings
    try:
        # read='mysql' handles quirks like backticks, # comments etc.
        sqlite_sqls = sqlglot.transpile(sql_content, read="mysql", write="sqlite")
    except Exception as e:
        print(f"SQLGlot parse error: {e}")
        return

    count = 0
    errors = 0
    
    for sql in sqlite_sqls:
        if not sql.strip():
            continue
            
        try:
            # Post-processing: SQLite doesn't like some constraints inline or specific types
            # sqlglot does a good job but let's be safe
            cursor.execute(sql)
            count += 1
        except Exception as e:
            # Ignore harmless errors
            if "already exists" not in str(e):
                # print(f"Error: {e} | SQL: {sql[:50]}...")
                errors += 1
                
    conn.commit()
    conn.close()
    print(f"Done! Executed {count} statements. Errors: {errors}")
    print(f"Created SQLite DB: {sqlite_file}")

if __name__ == "__main__":
    convert_mysql_to_sqlite("classicmodels.sql", "classicmodels.db")
