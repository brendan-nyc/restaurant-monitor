import os
from datetime import datetime, timedelta

from sqlalchemy import (
    Column, Integer, String, MetaData, Table,
    create_engine, delete, insert, select, text, update,
)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///restaurant_monitor.db")
# Render supplies postgres:// but SQLAlchemy requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
_meta = MetaData()

restaurants = Table("restaurants", _meta,
    Column("id", Integer, primary_key=True),
    Column("name", String, nullable=False),
    Column("platform", String, nullable=False),
    Column("url", String, nullable=False),
    Column("date", String, nullable=False),   # "" for recurring entries
    Column("party_size", Integer, nullable=False),
    Column("time_start", String, nullable=False),
    Column("time_end", String, nullable=False),
    Column("days_of_week", String),            # e.g. "thu,fri,sat"; NULL for specific-date
    Column("look_ahead_days", Integer),        # e.g. 45; NULL for specific-date
)

notified_slots = Table("notified_slots", _meta,
    Column("key", String, primary_key=True),
    Column("notified_at", String, nullable=False),
)


def init_db() -> None:
    _meta.create_all(engine)
    # Migrate: add columns introduced after the initial schema
    with engine.connect() as conn:
        for col, typedef in [("days_of_week", "TEXT"), ("look_ahead_days", "INTEGER")]:
            try:
                conn.execute(text(f"ALTER TABLE restaurants ADD COLUMN {col} {typedef}"))
                conn.commit()
            except Exception:
                pass  # column already exists


# ── Restaurants ───────────────────────────────────────────────────────────────

def get_all_restaurants() -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(select(restaurants)).fetchall()
    return [row._asdict() for row in rows]


def get_restaurant(rid: int) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            select(restaurants).where(restaurants.c.id == rid)
        ).fetchone()
    return row._asdict() if row else None


def _restaurant_values(data: dict) -> dict:
    return dict(
        name=data["name"],
        platform=data["platform"],
        url=data["url"],
        date=data.get("date", ""),
        party_size=int(data["party_size"]),
        time_start=data["time_start"],
        time_end=data["time_end"],
        days_of_week=data.get("days_of_week") or None,
        look_ahead_days=int(data["look_ahead_days"]) if data.get("look_ahead_days") else None,
    )


def add_restaurant(data: dict) -> None:
    with engine.connect() as conn:
        conn.execute(insert(restaurants).values(**_restaurant_values(data)))
        conn.commit()


def update_restaurant(rid: int, data: dict) -> None:
    with engine.connect() as conn:
        conn.execute(
            update(restaurants)
            .where(restaurants.c.id == rid)
            .values(**_restaurant_values(data))
        )
        conn.commit()


def delete_restaurant(rid: int) -> None:
    with engine.connect() as conn:
        conn.execute(delete(restaurants).where(restaurants.c.id == rid))
        conn.commit()


# ── Notified slots ────────────────────────────────────────────────────────────

def is_notified(key: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            select(notified_slots).where(notified_slots.c.key == key)
        ).fetchone()
    return row is not None


def mark_notified(key: str) -> None:
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    with engine.connect() as conn:
        conn.execute(delete(notified_slots).where(notified_slots.c.notified_at < cutoff))
        if not is_notified(key):
            conn.execute(insert(notified_slots).values(
                key=key, notified_at=datetime.now().isoformat()
            ))
        conn.commit()
