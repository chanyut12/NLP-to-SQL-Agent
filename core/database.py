from sqlalchemy import create_engine
from typing import Tuple, Optional
from sqlalchemy.engine import Engine

class ConnectionManager:
    @staticmethod
    def get_db_engine(db_type: str, db_config: dict) -> Tuple[Optional[Engine], Optional[str]]:
        """Create a database connection engine."""
        try:
            if db_type == "SQLite":
                db_path = f"sqlite:///{db_config['database']}"
            elif db_type == "MySQL":
                # Validation: Ensure User and Database are present (Password can be empty)
                if not db_config.get('user') or not db_config.get('database'):
                     return None, "MySQL requires at least User and Database Name."
                     
                # Ensure pymysql is installed or use default
                password = db_config.get('password', '')
                db_path = f"mysql+pymysql://{db_config['user']}:{password}@{db_config['host']}:{db_config['port']}/{db_config['database']}?charset=utf8mb4"
            elif db_type == "PostgreSQL":
                # Ensure psycopg2 is installed
                db_path = f"postgresql+psycopg2://{db_config['user']}:{db_config['password']}@{db_config['host']}:{db_config['port']}/{db_config['database']}"
            else:
                return None, f"Unsupported database type: {db_type}"
            
            engine = create_engine(db_path)
            # Test connection
            with engine.connect() as conn:
                pass
            return engine, None
        except Exception as e:
            return None, str(e)
