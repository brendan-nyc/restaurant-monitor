import os
from datetime import datetime, timedelta

from sqlalchemy import (
    Column, Integer, String, MetaData, Table,
    create_engine, delete, insert, select, update,
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
    Column("date", String, nullable=False),
    Column("party_size", Integer, nullable=False),
    Column("time_start", String, nullable=False),
    Column("time_end", String, nullable=False),
)

notified_slots = Table("notified_slots", _meta,
    Column("key", String, primary_key=True),
    Column("notified_at", String, nullable=False),
)


def init_db() -> None:
    _meta.create_all(engine)


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


def add_restaurant(data: dict) -> None:
    with engine.connect() as conn:
        conn.execute(insert(restaurants).values(
            name=data["name"],
            platform=data["platform"],
            url=data["url"],
            date=data["date"],
            party_size=int(data["party_size"]),
            time_start=data["time_start"],
            time_end=data["time_end"],
        ))
        conn.commit()


def update_restaurant(rid: int, data: dict) -> None:
    with engine.connect() as conn:
        conn.execute(
            update(restaurants)
            .where(restaurants.c.id == rid)
            .values(
                name=data["name"],
                platform=data["platform"],
                url=data["url"],
                date=data["date"],
                party_size=int(data["party_size"]),
                time_start=data["time_start"],
                time_end=data["time_end"],
            )
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
