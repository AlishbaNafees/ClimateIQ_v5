"""
scripts/csv_to_sqlite.py  —  ClimateIQ v5
══════════════════════════════════════════════════════════════════════════════
One-time conversion utility: reads your existing climate CSV and writes the
embedded SQLite database used by the application.

Usage
-----
    python scripts/csv_to_sqlite.py                         # auto-detect CSV
    python scripts/csv_to_sqlite.py path/to/data.csv        # explicit path
    python scripts/csv_to_sqlite.py path/to/data.csv --replace   # overwrite

Output
------
    database/climate_data.db   (created relative to project root)

The script applies every normalisation step that DataManager.load_csv() did in
v4 (alias resolution, sentiment normalisation, emotion/topic synthesis, date
parsing) so the database is fully pre-processed and ready for direct SQL use.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT    = _SCRIPT_DIR.parent
_DB_DIR     = _PROJECT / "database"
_DB_PATH    = _DB_DIR / "climate_data.db"
_TABLE      = "climate_tweets"

# ── Column aliases (identical to v4 DataManager) ──────────────────────────────
_ALIASES = {
    "text":      ["text", "tweet", "content", "message", "body",
                  "tweet_text", "tweettext", "cleaned_text", "lowercase_text"],
    "sentiment": ["sentiment", "label", "sentiment_label", "polarity",
                  "predicted_emotion"],
    "score":     ["score", "vader_score", "compound", "compound_score",
                  "sentiment_score", "sentimentscore"],
    "emotion":   ["predicted_emotion", "emotion_type", "emotion", "emotion_label",
                  "feeling", "emotiontype"],
    "topic":     ["predicted_topic", "topic", "category", "topic_label", "subject",
                  "climate_topic", "topic_category", "topiccategory"],
    "city":      ["city", "location", "region", "place", "city_name"],
    "date":      ["date", "created_at", "timestamp", "datetime",
                  "tweet_date", "post_date", "date_time"],
    "weather":   ["weather", "condition", "weather_condition",
                  "weather_type", "weather_data", "weatherdata"],
}


def _find_col(df: pd.DataFrame, canonical: str) -> str | None:
    cols_lower = {c.lower(): c for c in df.columns}
    for alias in _ALIASES.get(canonical, []):
        if alias in cols_lower:
            return cols_lower[alias]
    return None


def _normalise_sentiment(s) -> str:
    s = str(s).strip().lower()
    if s in ("pos", "positive", "1", "1.0", "2", "2.0"):    return "positive"
    if s in ("neg", "negative", "-1", "-1.0", "0", "0.0"):  return "negative"
    return "neutral"


_EMOTION_KEYWORDS = {
    "joy":      ["happy", "great", "wonderful", "love", "joy"],
    "anger":    ["angry", "anger", "outrage", "furious"],
    "fear":     ["fear", "scary", "afraid", "terrif"],
    "sadness":  ["sad", "disappoint", "mourn", "grief"],
    "surprise": ["surprise", "shock", "unexpect", "wow"],
    "disgust":  ["disgust", "horrible", "awful", "terrible"],
}

_TOPIC_KEYWORDS = {
    "temperature":   ["temperature", "heat", "hot", "cold", "warm", "freeze"],
    "air quality":   ["air", "pollution", "smog", "pm2.5", "aqi"],
    "flooding":      ["flood", "rain", "storm", "rainfall", "monsoon"],
    "drought":       ["drought", "dry", "water shortage", "arid"],
    "wildfire":      ["fire", "wildfire", "blaze", "burn"],
    "climate policy": ["policy", "agreement", "cop", "emission", "carbon", "treaty"],
}


def _guess_emotion(text: str) -> str:
    t = str(text).lower()
    for emotion, kw in _EMOTION_KEYWORDS.items():
        if any(k in t for k in kw):
            return emotion
    return "neutral"


def _guess_topic(text: str) -> str:
    t = str(text).lower()
    for topic, kw in _TOPIC_KEYWORDS.items():
        if any(k in t for k in kw):
            return topic
    return "general"


def _find_csv_auto() -> Path | None:
    """Look for any .csv in the project root or a data/ subfolder."""
    for pattern in ["*.csv", "data/*.csv", "dataset/*.csv"]:
        hits = list(_PROJECT.glob(pattern))
        if hits:
            return hits[0]
    return None


# ── Schema ────────────────────────────────────────────────────────────────────
_DDL = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    text        TEXT,
    sentiment   TEXT,
    score       REAL,
    emotion     TEXT,
    topic       TEXT,
    city        TEXT,
    tweet_date  TEXT,       -- ISO-8601  YYYY-MM-DD
    weather     TEXT
);
CREATE INDEX IF NOT EXISTS idx_city ON {_TABLE}(city);
CREATE INDEX IF NOT EXISTS idx_date ON {_TABLE}(tweet_date);
CREATE INDEX IF NOT EXISTS idx_sentiment ON {_TABLE}(sentiment);
CREATE INDEX IF NOT EXISTS idx_city_date ON {_TABLE}(city, tweet_date);
"""


# ── Main conversion ───────────────────────────────────────────────────────────
def convert(csv_path: Path, replace: bool = False) -> None:
    print(f"\n{'='*60}")
    print(f"  ClimateIQ v5 — CSV → SQLite Conversion")
    print(f"{'='*60}")
    print(f"  Source : {csv_path}")
    print(f"  Target : {_DB_PATH}\n")

    # ── Load CSV ──────────────────────────────────────────────────────────────
    print("  [1/5] Reading CSV …")
    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as exc:
        sys.exit(f"  ERROR reading CSV: {exc}")

    if df.empty:
        sys.exit("  ERROR: CSV is empty.")

    total_raw = len(df)
    print(f"        {total_raw:,} rows loaded, {len(df.columns)} columns detected.")

    # ── Resolve columns ───────────────────────────────────────────────────────
    print("  [2/5] Resolving column aliases …")
    col_map: dict[str, str] = {}
    for canonical in _ALIASES:
        found = _find_col(df, canonical)
        if found:
            col_map[canonical] = found
            print(f"        {canonical:12s} → '{found}'")
        else:
            print(f"        {canonical:12s} → (will be synthesised)")

    if "text" not in col_map:
        sys.exit(f"  ERROR: Cannot find a text column. Columns: {list(df.columns)}")

    # ── Normalise ─────────────────────────────────────────────────────────────
    print("  [3/5] Normalising data …")

    # Sentiment
    if "sentiment" in col_map:
        df[col_map["sentiment"]] = df[col_map["sentiment"]].apply(_normalise_sentiment)
    elif "score" in col_map:
        sc = pd.to_numeric(df[col_map["score"]], errors="coerce").fillna(0)
        df["_sentiment"] = sc.apply(
            lambda x: "positive" if x > 0.05 else ("negative" if x < -0.05 else "neutral")
        )
        col_map["sentiment"] = "_sentiment"
    else:
        df["_sentiment"] = "neutral"
        col_map["sentiment"] = "_sentiment"

    # Score
    if "score" in col_map:
        df[col_map["score"]] = pd.to_numeric(df[col_map["score"]], errors="coerce").fillna(0.0)
    else:
        smap = {"positive": 0.5, "neutral": 0.0, "negative": -0.5}
        df["_score"] = df[col_map["sentiment"]].map(smap).fillna(0.0)
        col_map["score"] = "_score"

    # Date
    if "date" in col_map:
        parsed = pd.to_datetime(df[col_map["date"]], errors="coerce")
        if parsed.dt.tz is not None:
            parsed = parsed.dt.tz_convert(None)
        df[col_map["date"]] = parsed
        df = df.dropna(subset=[col_map["date"]])
        df["_tweet_date"] = df[col_map["date"]].dt.strftime("%Y-%m-%d")
    else:
        df["_tweet_date"] = datetime.today().strftime("%Y-%m-%d")
    col_map["tweet_date"] = "_tweet_date"

    # Emotion (synthesise if missing)
    if "emotion" not in col_map:
        print("        Synthesising emotion column …")
        df["_emotion"] = df[col_map["text"]].apply(_guess_emotion)
        col_map["emotion"] = "_emotion"

    # Topic (synthesise if missing)
    if "topic" not in col_map:
        print("        Synthesising topic column …")
        df["_topic"] = df[col_map["text"]].apply(_guess_topic)
        col_map["topic"] = "_topic"

    # Weather & city
    if "weather" not in col_map:
        df["_weather"] = "Unknown"
        col_map["weather"] = "_weather"
    if "city" not in col_map:
        df["_city"] = "Unknown"
        col_map["city"] = "_city"

    print(f"        {len(df):,} rows after normalisation (dropped {total_raw - len(df):,} unparseable).")

    # ── Build output DataFrame ────────────────────────────────────────────────
    out = pd.DataFrame({
        "text":      df[col_map["text"]].astype(str),
        "sentiment": df[col_map["sentiment"]].astype(str),
        "score":     df[col_map["score"]].astype(float),
        "emotion":   df[col_map["emotion"]].astype(str),
        "topic":     df[col_map["topic"]].astype(str),
        "city":      df[col_map["city"]].astype(str),
        "tweet_date": df[col_map["tweet_date"]].astype(str),
        "weather":   df[col_map["weather"]].astype(str),
    })

    # ── Write SQLite ──────────────────────────────────────────────────────────
    print("  [4/5] Writing database …")
    _DB_DIR.mkdir(parents=True, exist_ok=True)

    if _DB_PATH.exists() and replace:
        _DB_PATH.unlink()
        print("        Existing database removed (--replace).")
    elif _DB_PATH.exists():
        sys.exit(
            f"  ERROR: {_DB_PATH} already exists.\n"
            "  Use  --replace  to overwrite."
        )

    with sqlite3.connect(_DB_PATH) as conn:
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        out.to_sql(_TABLE, conn, if_exists="append", index=False)
        conn.execute("PRAGMA journal_mode=WAL;")     # better concurrent reads
        conn.execute("PRAGMA synchronous=NORMAL;")   # safe + fast

    size_kb = _DB_PATH.stat().st_size / 1024
    print(f"        Written {len(out):,} rows → {size_kb:,.1f} KB")

    # ── Verify ────────────────────────────────────────────────────────────────
    print("  [5/5] Verifying …")
    with sqlite3.connect(_DB_PATH) as conn:
        count  = conn.execute(f"SELECT COUNT(*) FROM {_TABLE}").fetchone()[0]
        cities = conn.execute(f"SELECT COUNT(DISTINCT city) FROM {_TABLE}").fetchone()[0]
        dmin   = conn.execute(f"SELECT MIN(tweet_date) FROM {_TABLE}").fetchone()[0]
        dmax   = conn.execute(f"SELECT MAX(tweet_date) FROM {_TABLE}").fetchone()[0]

    print(f"        Records : {count:,}")
    print(f"        Cities  : {cities:,}")
    print(f"        Dates   : {dmin}  →  {dmax}")
    print(f"\n  ✅  Database ready at:  {_DB_PATH}\n")


# ── CLI entry-point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert a climate CSV into the ClimateIQ v5 SQLite database."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        help="Path to the source CSV file (auto-detected if omitted).",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Overwrite an existing database.",
    )
    args = parser.parse_args()

    if args.csv_path:
        csv_file = Path(args.csv_path)
        if not csv_file.exists():
            sys.exit(f"File not found: {csv_file}")
    else:
        csv_file = _find_csv_auto()
        if not csv_file:
            sys.exit(
                "No CSV file found automatically.\n"
                "Usage:  python scripts/csv_to_sqlite.py  path/to/data.csv"
            )
        print(f"  Auto-detected: {csv_file}")

    convert(csv_file, replace=args.replace)
