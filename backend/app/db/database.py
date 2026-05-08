from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# backend/ root, resolved relative to this file so it works from any CWD.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_DB_PATH = (_BACKEND_ROOT / "data" / "lms.db").as_posix()
(_BACKEND_ROOT / "data").mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite:///{_DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()