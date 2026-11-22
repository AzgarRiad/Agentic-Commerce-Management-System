"""Database configuration for ACMS.

Set ``DB_URL`` to use an external database. A project-local SQLite database is
used for development when no URL is configured.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.database_models import Base

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = BASE_DIR / "data" / "acms.db"
DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

db_url = os.getenv("DB_URL") or f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
engine_options = {"pool_pre_ping": True}
if db_url.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(db_url, **engine_options)
session = sessionmaker(autoflush=False, bind=engine)

# Ensure a fresh local install has the tables required by the agent.
Base.metadata.create_all(bind=engine)
