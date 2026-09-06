"""
core/db_manager.py  —  ClimateIQ v5
══════════════════════════════════════════════════════════════════════════════
SQLite database manager (replaces manual CSV loading).

Responsibilities:
  - Locate or create the embedded database at  database/climate_data.db
  - Provide city list, date range, and filtered DataFrames via SQL queries
  - Keep all column-alias and sentiment-normalisation logic from v4 intact

Database schema (single table):
  climate_tweets
    id          INTEGER PRIMARY KEY AUTOINCREMENT
    text        TEXT
    sentiment   TEXT        -- 'positive' | 'negative' | 'neutral'
    score       REAL
    emotion     TEXT
    topic       TEXT
    city        TEXT
    tweet_date  TEXT        -- ISO-8601 'YYYY-MM-DD'
    weather     TEXT

Design notes:
  - tweet_date stored as TEXT (ISO-8601) for fast BETWEEN queries
  - All heavy normalisation happens once in the conversion script
  - filter_data() uses parameterised SQL — no string interpolation
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path
from typing import List, Tuple

import pandas as pd

# ── Path resolution ───────────────────────────────────────────────────────────
# database/ lives next to the core/ package, one level up from this file.
_HERE   = Path(__file__).resolve().parent          # core/
_ROOT   = _HERE.parent                              # project root
DB_PATH = _ROOT / "database" / "climate_data.db"

TABLE   = "climate_tweets"


class DatabaseManager:
    """
    Lightweight SQLite gateway for ClimateIQ v5.

    Usage (singleton already created at module bottom):
        from core.db_manager import db_manager
        ok, msg = db_manager.initialise()
        cities  = db_manager.city_list()
        df      = db_manager.filter_data("Karachi", date(2023,1,1), date(2023,12,31))
    """

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path   = db_path
        self.is_loaded  = False
        self._col_map   = self._default_col_map()

    # ── Public API ─────────────────────────────────────────────────────────────

    def initialise(self) -> Tuple[bool, str]:
        """
        Check that the database exists and contains data.
        Returns (True, message) or (False, error).
        """
        if not self._db_path.exists():
            return False, (
                f"Database not found at:\n{self._db_path}\n\n"
                "Run  scripts/csv_to_sqlite.py  to create it."
            )

        try:
            count = self._scalar(f"SELECT COUNT(*) FROM {TABLE}")
        except Exception as exc:
            return False, f"Database error:\n{exc}"

        if count == 0:
            return False, "Database exists but contains no records."

        self.is_loaded = True
        return True, f"Database loaded — {count:,} records available."

    def city_list(self) -> List[str]:
        """Return sorted list of unique city names (fast index-only scan)."""
        if not self.is_loaded:
            return []
        rows = self._fetchall(
            f"SELECT DISTINCT city FROM {TABLE} WHERE city IS NOT NULL ORDER BY city"
        )
        return [r[0] for r in rows if r[0] and r[0].strip()]

    def date_range(self) -> Tuple[date, date]:
        """Return (min_date, max_date) from the database."""
        if not self.is_loaded:
            today = date.today()
            return today, today
        row = self._fetchone(
            f"SELECT MIN(tweet_date), MAX(tweet_date) FROM {TABLE}"
        )
        try:
            mn = date.fromisoformat(row[0])
            mx = date.fromisoformat(row[1])
            return mn, mx
        except Exception:
            today = date.today()
            return today, today

    def filter_data(
        self,
        city: str,
        start: date,
        end: date,
        limit: int = 50_000,
    ) -> pd.DataFrame:
        """
        Return a filtered DataFrame using efficient parameterised SQL.

        Parameters
        ----------
        city    : exact city name, or 'All Cities' / '' to skip city filter
        start   : inclusive start date
        end     : inclusive end date
        limit   : max rows returned (guards against runaway queries)
        """
        if not self.is_loaded:
            return pd.DataFrame()

        s_str = start.isoformat()
        e_str = end.isoformat()

        all_cities = city.lower() in ("all cities", "all", "")

        if all_cities:
            sql = f"""
                SELECT text, sentiment, score, emotion, topic, city,
                       tweet_date AS date, weather
                FROM   {TABLE}
                WHERE  tweet_date BETWEEN ? AND ?
                ORDER  BY tweet_date
                LIMIT  ?
            """
            params = (s_str, e_str, limit)
        else:
            sql = f"""
                SELECT text, sentiment, score, emotion, topic, city,
                       tweet_date AS date, weather
                FROM   {TABLE}
                WHERE  tweet_date BETWEEN ? AND ?
                  AND  LOWER(city) = LOWER(?)
                ORDER  BY tweet_date
                LIMIT  ?
            """
            params = (s_str, e_str, city, limit)

        df = self._query_df(sql, params)

        # Coerce types expected by chart_engine / pdf_reporter
        if not df.empty:
            df["score"]    = pd.to_numeric(df["score"],    errors="coerce").fillna(0.0)
            df["date"]     = pd.to_datetime(df["date"],    errors="coerce")
            df["sentiment"] = df["sentiment"].fillna("neutral")

        return df

    def compute_stats(self, df: pd.DataFrame) -> dict:
        """
        Compute summary statistics from a filtered DataFrame.
        Mirrors DataManager.compute_stats() so the rest of the app is unchanged.
        """
        if df.empty:
            return {}

        cmap  = self._col_map
        total = len(df)
        sents = df["sentiment"].str.lower()

        pos = int((sents == "positive").sum())
        neg = int((sents == "negative").sum())
        neu = int((sents == "neutral").sum())

        avg_score = round(float(df["score"].mean()), 4)

        cities_n  = int(df["city"].nunique())
        top_city  = df["city"].value_counts().index[0] if not df["city"].empty else "—"
        top_emotion = (
            df["emotion"].value_counts().index[0]
            if "emotion" in df.columns and not df["emotion"].empty else "—"
        )
        top_topic = (
            df["topic"].value_counts().index[0]
            if "topic" in df.columns and not df["topic"].empty else "—"
        )

        span_days    = 0
        actual_start = None
        actual_end   = None
        if "date" in df.columns and not df.empty:
            actual_min   = df["date"].min()
            actual_max   = df["date"].max()
            span_days    = int((actual_max - actual_min).days) + 1
            actual_start = actual_min.date()
            actual_end   = actual_max.date()

        avg_words = round(float(df["text"].astype(str).apply(lambda x: len(x.split())).mean()), 1)

        return {
            "total":        total,
            "positive":     pos,
            "negative":     neg,
            "neutral":      neu,
            "pos_pct":      round(100 * pos / total, 1) if total else 0,
            "neg_pct":      round(100 * neg / total, 1) if total else 0,
            "neu_pct":      round(100 * neu / total, 1) if total else 0,
            "avg_score":    avg_score,
            "cities_n":     cities_n,
            "top_city":     str(top_city),
            "top_emotion":  str(top_emotion),
            "top_topic":    str(top_topic),
            "span_days":    span_days,
            "avg_words":    avg_words,
            "actual_start": actual_start,
            "actual_end":   actual_end,
            "_col_map":     cmap,
        }

    # ── Column-map (keeps chart_engine happy) ─────────────────────────────────

    @staticmethod
    def _default_col_map() -> dict:
        """
        Maps canonical names → actual DataFrame column names produced by
        filter_data().  chart_engine / pdf_reporter consume this dict.
        """
        return {
            "text":      "text",
            "sentiment": "sentiment",
            "score":     "score",
            "emotion":   "emotion",
            "topic":     "topic",
            "city":      "city",
            "date":      "date",
            "weather":   "weather",
        }

    # ── SQLite helpers ────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _scalar(self, sql: str, params: tuple = ()) -> int:
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else 0

    def _fetchone(self, sql: str, params: tuple = ()):
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchone()

    def _fetchall(self, sql: str, params: tuple = ()):
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            return cur.fetchall()

    def _query_df(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(sql, conn, params=params)


# ── Singleton ─────────────────────────────────────────────────────────────────
db_manager = DatabaseManager()
