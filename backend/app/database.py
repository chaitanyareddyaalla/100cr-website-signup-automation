import os
from pathlib import Path
import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "signup_automation.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def get_engine():
    url = get_database_url()
    if url.startswith("sqlite"):
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_db_session() -> Session:
    session = SessionLocal()
    try:
        return session
    finally:
        pass


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection
