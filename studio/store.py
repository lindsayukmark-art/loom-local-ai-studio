from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def new_id():
    return uuid.uuid4().hex


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, body TEXT NOT NULL)')

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def put_job(self, job):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)', (job['id'], json.dumps(job)))

    def get_job(self, job_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM jobs WHERE id=?', (job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def jobs(self, limit=100):
        with self.connect() as db:
            rows = db.execute('SELECT body FROM jobs ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put_asset(self, asset):
        with self.connect() as db:
            db.execute('INSERT INTO assets VALUES (?,?)', (asset['id'], json.dumps(asset)))

    def get_asset(self, asset_id):
        with self.connect() as db:
            row = db.execute('SELECT body FROM assets WHERE id=?', (asset_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def assets(self, limit=200):
        with self.connect() as db:
            rows = db.execute('SELECT body FROM assets ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def interrupt_pending(self):
        with self.connect() as db:
            rows = db.execute('SELECT body FROM jobs').fetchall()
            for row in rows:
                job = json.loads(row[0])
                if job['status'] in {'queued', 'running'}:
                    job.update(status='interrupted', error='The app closed before this job finished. Submit it again to retry.')
                    db.execute('UPDATE jobs SET body=? WHERE id=?', (json.dumps(job), job['id']))


def public_asset(asset):
    return {key: value for key, value in asset.items() if key != 'path'}
