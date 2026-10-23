"""
Data Layer (Section 9, Layer 5)

SQLite for local development, PostgreSQL for anything beyond a
single-user demo, both through the same SQLAlchemy ORM code so the
migration path is just swapping DATABASE_URL — no rewrite.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default: local SQLite file next to this module (dev).
# Set DATABASE_URL to a postgresql:// URL in production (see docker-compose.yml).
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'medbox.db')}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _migrate_sqlite_columns():
    """Ensure newly added columns exist in existing SQLite databases."""
    with engine.connect() as conn:
        for table, col, col_type in [
            ("recognition_history", "detected_exp", "VARCHAR"),
            ("recognition_history", "date_confidence", "FLOAT DEFAULT 0.0"),
        ]:
            try:
                # Check if column exists
                cols = [c[1] for c in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()]
                if col not in cols:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                    conn.commit()
            except Exception:
                pass


def init_db():
    """Create tables and seed demo data on startup."""
    from backend import models  # noqa: F401 (registers models on Base metadata)

    models.Base.metadata.create_all(bind=engine)
    _migrate_sqlite_columns()

    db = SessionLocal()
    try:
        from backend.seed import seed_if_empty

        seed_if_empty(db)
    finally:
        db.close()

