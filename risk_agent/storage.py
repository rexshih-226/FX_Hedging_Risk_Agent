"""Immutable preparation snapshots, idempotent reviews and source snapshots."""
import json
import sqlite3
from pathlib import Path


class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            case_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
            request_json TEXT NOT NULL, response_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reviews (
            case_id TEXT NOT NULL, request_hash TEXT NOT NULL,
            proposal_id TEXT NOT NULL, proposal_version INTEGER NOT NULL,
            request_json TEXT NOT NULL, response_json TEXT NOT NULL,
            PRIMARY KEY(case_id, request_hash),
            UNIQUE(case_id, proposal_id, proposal_version)
        );
        CREATE TABLE IF NOT EXISTS source_snapshots (
            snapshot_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS policies (
            policy_hash TEXT PRIMARY KEY, version TEXT UNIQUE NOT NULL, policy_json TEXT NOT NULL
        );
        """)

    def close(self):
        self.db.close()

    def save_policy(self, policy_hash, policy):
        row = self.db.execute("SELECT policy_hash FROM policies WHERE version=?", (policy["version"],)).fetchone()
        if row and row[0] != policy_hash:
            raise ValueError("政策版本已存在且內容不同；修改政策必須增加 version")
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO policies VALUES(?,?,?)", (policy_hash, policy["version"], json.dumps(policy)))

    def case(self, case_id):
        row = self.db.execute("SELECT request_hash, request_json, response_json FROM cases WHERE case_id=?", (case_id,)).fetchone()
        return (row[0], json.loads(row[1]), json.loads(row[2])) if row else None

    def save_case(self, request_hash, request, response):
        with self.db:
            self.db.execute("INSERT INTO cases VALUES(?,?,?,?)", (request["case_id"], request_hash, json.dumps(request), json.dumps(response)))

    def reviews(self, case_id):
        rows = self.db.execute("SELECT request_hash, request_json, response_json FROM reviews WHERE case_id=? ORDER BY rowid", (case_id,)).fetchall()
        return [(r[0], json.loads(r[1]), json.loads(r[2])) for r in rows]

    def save_review(self, request_hash, request, response):
        p = request["proposal"]
        with self.db:
            self.db.execute("INSERT INTO reviews VALUES(?,?,?,?,?,?)", (request["case_id"], request_hash, p["proposal_id"], p["version"], json.dumps(request), json.dumps(response)))

    def save_source(self, metadata):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO source_snapshots VALUES(?,?)", (metadata["snapshot_id"], json.dumps(metadata)))
