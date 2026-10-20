"""SQLite storage. Streamlit Cloud wipes local files on restart, so init() rebuilds
everything it needs on every boot (tables + the demo profile)."""
import datetime as dt
import json
import sqlite3
import threading
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "scholarforge.db"
SEED_PATH = ROOT / "data" / "seed_opportunities.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT, plan TEXT);
CREATE TABLE IF NOT EXISTS run_steps (run_id TEXT, step TEXT, label TEXT, status TEXT, started_at TEXT,
    finished_at TEXT, items INTEGER, detail TEXT, PRIMARY KEY (run_id, step));
CREATE TABLE IF NOT EXISTS run_items (run_id TEXT, opp_id TEXT, position INTEGER, data TEXT, PRIMARY KEY (run_id, opp_id));
CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, run_id TEXT, agent TEXT, event TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS weights (type TEXT PRIMARY KEY, weight REAL NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, opp_id TEXT, type TEXT, decision TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, kind TEXT, content TEXT,
    image BLOB, image_mime TEXT, processed INTEGER DEFAULT 0);
"""


def now() -> dt.datetime:
    return dt.datetime.now(IST)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


@st.cache_resource
def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    from core.profile import DEMO_PROFILE  # local import avoids a cycle
    if conn.execute("SELECT 1 FROM profile WHERE id = 1").fetchone() is None:
        conn.execute("INSERT INTO profile (id, data, updated_at) VALUES (1, ?, ?)",
                     (json.dumps(DEMO_PROFILE), now_iso()))
        conn.commit()
    return conn


def init() -> None:
    _conn()


def _write(sql: str, params=()) -> None:
    with _lock:
        c = _conn()
        c.execute(sql, params)
        c.commit()


def _read(sql: str, params=()) -> list[sqlite3.Row]:
    with _lock:
        return _conn().execute(sql, params).fetchall()


# --- profile -----------------------------------------------------------------
def get_profile() -> dict:
    row = _read("SELECT data FROM profile WHERE id = 1")
    return json.loads(row[0]["data"]) if row else {}


def save_profile(profile: dict) -> None:
    _write("INSERT INTO profile (id, data, updated_at) VALUES (1, ?, ?) "
           "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
           (json.dumps(profile), now_iso()))


# --- seed samples --------------------------------------------------------------
def load_samples() -> list[dict]:
    items = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    stamp = now_iso()
    for it in items:
        it["fetched_at"] = stamp
    return items


# --- runs ----------------------------------------------------------------------
def create_run(run_id: str) -> None:
    _write("INSERT INTO runs (id, started_at, status) VALUES (?, ?, 'running')", (run_id, now_iso()))


def finish_run(run_id: str, status: str, plan: dict | None) -> None:
    _write("UPDATE runs SET finished_at = ?, status = ?, plan = ? WHERE id = ?",
           (now_iso(), status, json.dumps(plan or {}), run_id))


def save_step(run_id, step, label, status, started_at, items=0, detail="") -> None:
    _write("INSERT INTO run_steps (run_id, step, label, status, started_at, finished_at, items, detail) "
           "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(run_id, step) DO UPDATE SET status = excluded.status, "
           "finished_at = excluded.finished_at, items = excluded.items, detail = excluded.detail",
           (run_id, step, label, status, started_at, now_iso(), items, detail))


def save_items(run_id: str, items: list[dict]) -> None:
    with _lock:
        c = _conn()
        c.execute("DELETE FROM run_items WHERE run_id = ?", (run_id,))
        c.executemany("INSERT INTO run_items (run_id, opp_id, position, data) VALUES (?, ?, ?, ?)",
                      [(run_id, it["id"], i, json.dumps(it)) for i, it in enumerate(items)])
        c.commit()


def latest_run() -> dict | None:
    row = _read("SELECT * FROM runs ORDER BY started_at DESC LIMIT 1")
    return dict(row[0]) if row else None


def run_steps(run_id: str) -> list[dict]:
    return [dict(r) for r in _read("SELECT * FROM run_steps WHERE run_id = ? ORDER BY started_at, step", (run_id,))]


def run_items(run_id: str) -> list[dict]:
    return [json.loads(r["data"]) for r in _read("SELECT data FROM run_items WHERE run_id = ? ORDER BY position", (run_id,))]


# --- audit log -------------------------------------------------------------------
def audit(run_id: str | None, agent: str, event: str, detail: str = "") -> None:
    _write("INSERT INTO audit_log (ts, run_id, agent, event, detail) VALUES (?, ?, ?, ?, ?)",
           (now_iso(), run_id, agent, event, detail))


def audit_rows(limit: int = 300) -> list[dict]:
    return [dict(r) for r in _read("SELECT ts, run_id, agent, event, detail FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))]


# --- memory (learning arrives Thu; tables exist from day 1) ------------------------
def get_weights() -> dict:
    return {r["type"]: r["weight"] for r in _read("SELECT type, weight FROM weights")}


def unprocessed_inbox() -> list[dict]:
    return [dict(r) for r in _read("SELECT * FROM inbox WHERE processed = 0 ORDER BY id")]
