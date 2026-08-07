"""The audit log: every AI attempt and every draft's outcome, in a small
database on this Mac (private/ is never uploaded). For any listing it answers:
which model said what, which checks it failed, what it cost, and why the draft
ended up ready or with you."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

AUDIT_DB = Path(__file__).resolve().parent.parent / "private" / "audit.sqlite3"

TABLES = """
create table if not exists attempts (
    id integer primary key, at text, item_id text, model text, answer text, error text,
    problems text, tokens_in integer, tokens_out integer, seconds real, cost_pence text);
create table if not exists drafts (
    id integer primary key, at text, item_id text, status text, reasons text, title text, answer text);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AuditLog:
    def __init__(self, path=AUDIT_DB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(TABLES)

    def attempt(self, item_id, reply, problems, cost):
        self.db.execute(
            "insert into attempts (at, item_id, model, answer, error, problems, tokens_in, tokens_out, seconds,"
            " cost_pence) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now(), item_id, reply.model, json.dumps(reply.answer, ensure_ascii=False), reply.error,
             json.dumps(problems, ensure_ascii=False), reply.tokens_in, reply.tokens_out, reply.seconds, str(cost)))
        self.db.commit()

    def draft(self, result):
        self.db.execute(
            "insert into drafts (at, item_id, status, reasons, title, answer) values (?, ?, ?, ?, ?, ?)",
            (now(), result["item_id"], result["status"], json.dumps(result["reasons"], ensure_ascii=False),
             result["title"], json.dumps(result["answer"], ensure_ascii=False)))
        self.db.commit()
