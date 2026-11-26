from contextlib import closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3

from translator import Result


def connect():
    folder = Path.home() / ".vajehnegar"
    folder.mkdir(exist_ok=True)
    db = sqlite3.connect(folder / "documents.sqlite3", timeout=10)
    db.execute("CREATE TABLE IF NOT EXISTS docs (id TEXT PRIMARY KEY, title TEXT, payload TEXT, updated TEXT)")
    return db


def save(job, src, dst):
    data = dict(job, items=[asdict(item) for item in job["items"]], running=False, src=src, dst=dst)
    with closing(connect()) as db, db:
        db.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?,strftime('%Y-%m-%d %H:%M:%f','now'))",
                   (job["id"], job["parts"][0][:64], json.dumps(data, ensure_ascii=False)))


def choices():
    with closing(connect()) as db:
        return dict(db.execute("SELECT id,title FROM docs ORDER BY updated DESC"))


def load(key):
    with closing(connect()) as db:
        data = json.loads(db.execute("SELECT payload FROM docs WHERE id=?", (key,)).fetchone()[0])
    data["items"] = [Result(**item) for item in data["items"]]
    return data
