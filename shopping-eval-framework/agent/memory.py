"""
User memory system for long-horizon, personalised shopping sessions.

Maintains user profiles, explicit/implicit preferences, and purchase history
in a local SQLite database. Enables simulation of returning-user behaviour.

Two memory types:
  explicit  — user directly stated a preference ("I prefer minimalist design")
  implicit  — agent inferred from behaviour (bought neutral-toned item → inferred palette)
These have different reliability profiles: explicit is authoritative,
implicit should be weighted lower and can be overridden.

Usage:
    from agent.memory import MemoryManager
    mm = MemoryManager()
    ctx = mm.get_user_context("user_001")
    mm.add_preference("user_001", "style", "minimalist", "explicit")
    mm.add_purchase("user_001", "ce_003", "Sony WH-1000XM5", "consumer_electronics")
    mm.should_avoid("user_001", "ce_003")   # True — recently purchased
"""
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_AGENT_DIR, "memory.db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id    TEXT PRIMARY KEY,
    name       TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id          TEXT,
    preference_key   TEXT,
    preference_value TEXT,
    memory_type      TEXT CHECK(memory_type IN ('implicit', 'explicit')),
    confidence       FLOAT DEFAULT 1.0,
    last_updated     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, preference_key)
);

CREATE TABLE IF NOT EXISTS purchase_history (
    user_id      TEXT,
    product_id   TEXT,
    product_name TEXT,
    category     TEXT,
    purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    occasion     TEXT
);
"""

_DEMO_USERS = [
    {
        "user_id": "user_001",
        "name": "Alex",
        "preferences": [
            ("style", "minimalist", "explicit", 1.0),
            ("color_palette", "neutral tones", "implicit", 0.75),
            ("brand_affinity", "Sony", "implicit", 0.6),
        ],
        "purchases": [
            # Bought a lamp for a birthday last month — should_avoid returns True
            ("lamp_001", "Brightech Sparq LED Floor Lamp",
             "home_decor", "birthday gift",
             datetime.now(timezone.utc) - timedelta(days=28)),
        ],
    },
    {
        "user_id": "user_002",
        "name": "Jordan",
        "preferences": [
            ("budget_sensitivity", "high", "explicit", 0.9),
            ("max_price", "150", "explicit", 1.0),
            ("preferred_category", "consumer_electronics", "implicit", 0.7),
        ],
        "purchases": [
            # Bought headphones 3 weeks ago — should_avoid returns True
            ("ce_003", "Sony WH-1000XM5 Wireless Headphones",
             "consumer_electronics", None,
             datetime.now(timezone.utc) - timedelta(days=21)),
        ],
    },
]


class MemoryManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self._seed_if_empty()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_CREATE_SQL)
            conn.commit()

    def _seed_if_empty(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM user_profiles"
            ).fetchone()[0]
        if count > 0:
            return

        for user in _DEMO_USERS:
            self.add_user(user["user_id"], user["name"])
            for key, value, mtype, conf in user["preferences"]:
                self.add_preference(
                    user["user_id"], key, value, mtype, confidence=conf
                )
            for product_id, product_name, category, occasion, ts in user["purchases"]:
                self._add_purchase_at(
                    user["user_id"], product_id, product_name,
                    category, occasion, ts
                )

    def add_user(self, user_id: str, name: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_profiles (user_id, name) VALUES (?, ?)",
                (user_id, name),
            )
            conn.commit()

    def add_preference(
        self,
        user_id: str,
        key: str,
        value: str,
        memory_type: str,
        confidence: float = 1.0,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_preferences
                    (user_id, preference_key, preference_value,
                     memory_type, confidence, last_updated)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, preference_key) DO UPDATE SET
                    preference_value = excluded.preference_value,
                    memory_type = excluded.memory_type,
                    confidence = excluded.confidence,
                    last_updated = excluded.last_updated
                """,
                (user_id, key, value, memory_type, confidence, now),
            )
            conn.commit()

    def add_purchase(
        self,
        user_id: str,
        product_id: str,
        product_name: str,
        category: str,
        occasion: Optional[str] = None,
    ) -> None:
        self._add_purchase_at(
            user_id, product_id, product_name, category, occasion,
            datetime.now(timezone.utc),
        )

    def _add_purchase_at(
        self,
        user_id: str,
        product_id: str,
        product_name: str,
        category: str,
        occasion: Optional[str],
        ts: datetime,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO purchase_history
                    (user_id, product_id, product_name, category, purchased_at, occasion)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, product_id, product_name, category, ts.isoformat(), occasion),
            )
            conn.commit()

    def get_user_context(self, user_id: str) -> dict:
        """
        Return a dict with:
          name         — display name
          preferences  — {key: {value, memory_type, confidence}}
          purchases    — last 5 purchases [{product_id, product_name, category, occasion}]
          avoid_ids    — product IDs purchased in the last 90 days
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            profile = conn.execute(
                "SELECT name FROM user_profiles WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not profile:
                return {}

            pref_rows = conn.execute(
                "SELECT preference_key, preference_value, memory_type, confidence "
                "FROM user_preferences WHERE user_id = ? "
                "ORDER BY confidence DESC",
                (user_id,),
            ).fetchall()

            purchase_rows = conn.execute(
                "SELECT product_id, product_name, category, occasion, purchased_at "
                "FROM purchase_history WHERE user_id = ? "
                "ORDER BY purchased_at DESC LIMIT 5",
                (user_id,),
            ).fetchall()

        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            recent_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT product_id FROM purchase_history "
                    "WHERE user_id = ? AND purchased_at > ?",
                    (user_id, cutoff),
                ).fetchall()
            ]

        return {
            "name": profile["name"],
            "preferences": {
                row["preference_key"]: {
                    "value": row["preference_value"],
                    "memory_type": row["memory_type"],
                    "confidence": row["confidence"],
                }
                for row in pref_rows
            },
            "purchases": [
                {
                    "product_id": row["product_id"],
                    "product_name": row["product_name"],
                    "category": row["category"],
                    "occasion": row["occasion"],
                }
                for row in purchase_rows
            ],
            "avoid_ids": recent_ids,
        }

    def should_avoid(self, user_id: str, product_id: str) -> bool:
        """Return True if the product was purchased by this user in the last 90 days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM purchase_history "
                "WHERE user_id = ? AND product_id = ? AND purchased_at > ?",
                (user_id, product_id, cutoff),
            ).fetchone()
        return row is not None
