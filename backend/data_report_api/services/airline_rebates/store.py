"""Local pilot storage. No shared database is used."""
from contextlib import closing, contextmanager
from pathlib import Path
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS rebate_policies (
  id TEXT PRIMARY KEY, profile TEXT NOT NULL, original BLOB NOT NULL,
  confirmed_by TEXT, confirmed_at TEXT
);
CREATE TABLE IF NOT EXISTS rebate_tasks (
  id TEXT PRIMARY KEY, policy_id TEXT NOT NULL UNIQUE REFERENCES rebate_policies(id),
  profile TEXT NOT NULL, run_token TEXT, run_at INTEGER, current_run TEXT, run_error TEXT
);
CREATE TABLE IF NOT EXISTS rebate_runs (
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES rebate_tasks(id), summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rebate_days (
  run_id TEXT NOT NULL REFERENCES rebate_runs(id), day TEXT NOT NULL, details TEXT NOT NULL,
  PRIMARY KEY (run_id, day)
);
"""


@contextmanager
def connect(directory):
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with closing(sqlite3.connect(root / "hkg26003.sqlite3", timeout=15)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA)
        yield db


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
