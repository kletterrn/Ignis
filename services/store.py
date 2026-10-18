import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

def utcnow():
    return datetime.now(timezone.utc).isoformat()

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL,id TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(kind,id)); CREATE TABLE IF NOT EXISTS outbox (id INTEGER PRIMARY KEY AUTOINCREMENT,body TEXT NOT NULL,error TEXT);")

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, kind, record):
        with self.db() as db:
            db.execute("INSERT INTO records VALUES (?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body", (kind, record["id"], json.dumps(record, allow_nan=False)))
        return record

    def get(self, kind, key):
        with self.db() as db:
            row = db.execute("SELECT body FROM records WHERE kind=? AND id=?", (kind, key)).fetchone()
        return json.loads(row[0]) if row else None

    def all(self, kind):
        with self.db() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM records WHERE kind=? ORDER BY id", (kind,))]

    def queue(self, body):
        with self.db() as db:
            db.execute("INSERT INTO outbox(body) VALUES (?)", (json.dumps(body, allow_nan=False),))

    def pending(self):
        with self.db() as db:
            return [{"id": row[0], "body": json.loads(row[1]), "error": row[2]} for row in db.execute("SELECT id,body,error FROM outbox ORDER BY id")]

    def delivered(self, key):
        with self.db() as db:
            db.execute("DELETE FROM outbox WHERE id=?", (key,))

    def failed(self, key):
        with self.db() as db:
            db.execute("UPDATE outbox SET error='Cloud publication failed; retry required' WHERE id=?", (key,))
