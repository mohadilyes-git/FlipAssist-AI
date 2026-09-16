"""The audit log: every AI attempt and every draft's outcome, in a small
database on this Mac (private/ is never uploaded). For any listing it answers:
which model said what, which checks it failed, what it cost, and why the draft
ended up ready or with you. It also keeps what you actually sent for a draft
(flip.api's approve), so the results can count how often a draft was right as
it was, and it adds it all up for the cost meter (stats)."""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

AUDIT_DB = Path(__file__).resolve().parent.parent / "private" / "audit.sqlite3"

TABLES = """
create table if not exists attempts (
    id integer primary key, at text, item_id text, model text, answer text, error text,
    problems text, tokens_in integer, tokens_out integer, seconds real, cost_pence text, job text);
create table if not exists drafts (
    id integer primary key, at text, item_id text, status text, reasons text, title text, answer text, job text,
    listing text);
create table if not exists approvals (
    id integer primary key, at text, draft_id integer references drafts(id), sent text, edited integer);
"""
# what a draft's text is, for each job: the message, or the listing's description
DRAFTED = {"message": "message", "listing": "description"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pence(text):
    try:
        return Decimal(text)
    except (InvalidOperation, TypeError):
        return Decimal(0)


class AuditLog:
    def __init__(self, path=AUDIT_DB):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)  # the API answers from more than one thread
        self.lock = threading.Lock()
        self.db.executescript(TABLES)
        columns = {row[1] for row in self.db.execute("pragma table_info(drafts)")}
        for column in ("job", "listing"):  # a log from before the API, or before approving taught your style
            if column not in columns:
                self.db.execute(f"alter table drafts add column {column} text")
        if "job" not in {row[1] for row in self.db.execute("pragma table_info(attempts)")}:  # before colour looks
            self.db.execute("alter table attempts add column job text")

    def attempt(self, item_id, reply, problems, cost, job="draft"):
        """Keep one attempt. job: "draft", or "colour" for a second look at the colour alone."""
        with self.lock:
            self.db.execute(
                "insert into attempts (at, item_id, model, answer, error, problems, tokens_in, tokens_out, seconds,"
                " cost_pence, job) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (now(), item_id, reply.model, json.dumps(reply.answer, ensure_ascii=False), reply.error,
                 json.dumps(problems, ensure_ascii=False), reply.tokens_in, reply.tokens_out, reply.seconds, str(cost),
                 job))
            self.db.commit()

    def draft(self, result):
        """Keep a draft's outcome. Its id goes into result["draft_id"], for approving it later."""
        job = "message" if "offer" in result else "listing"
        with self.lock:
            cursor = self.db.execute(
                "insert into drafts (at, item_id, status, reasons, title, answer, job, listing)"
                " values (?, ?, ?, ?, ?, ?, ?, ?)",
                (now(), result["item_id"], result["status"], json.dumps(result["reasons"], ensure_ascii=False),
                 result["title"], json.dumps(result["answer"], ensure_ascii=False), job,
                 json.dumps(result.get("listing"), ensure_ascii=False)))
            self.db.commit()
        result["draft_id"] = cursor.lastrowid
        return cursor.lastrowid

    def approve(self, draft_id, sent):
        """Keep what you actually sent for a draft, and whether you changed it
        first (spaces aside). None if there's no such draft. A draft has one
        approval: approving it again (a retry, a second tap, a later edit)
        replaces the first, so it's counted once."""
        with self.lock:
            row = self.db.execute("select job, answer from drafts where id = ?", (draft_id,)).fetchone()
            if row is None:
                return None
            job, answer = row
            drafted = (json.loads(answer) or {}).get(DRAFTED.get(job, "message")) or ""
            edited = " ".join(sent.split()) != " ".join(drafted.split())
            at = now()
            replaced = self.db.execute("update approvals set at = ?, sent = ?, edited = ? where draft_id = ?",
                                       (at, sent, int(edited), draft_id)).rowcount
            if not replaced:
                self.db.execute("insert into approvals (at, draft_id, sent, edited) values (?, ?, ?, ?)",
                                (at, draft_id, sent, int(edited)))
            self.db.commit()
        return {"draft_id": draft_id, "edited": edited, "at": at}

    def listing(self, draft_id):
        """The listing a message was drafted for (its title, asking_price and
        marketplace), or None: a listing's draft, or a draft from before."""
        with self.lock:
            row = self.db.execute("select listing from drafts where id = ? and job = 'message'", (draft_id,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def stats(self):
        """The cost meter: how drafts ended, which model did the work, what it
        cost, and how often you changed a draft before sending it. "Done on
        this Mac" is the share of passing answers that came from the template
        or the local model, not the paid API. A look at the colour alone is
        counted in its model's attempts and cost, but it didn't write the draft."""
        with self.lock:
            ended = dict(self.db.execute("select status, count(*) from drafts group by status").fetchall())
            rows = self.db.execute("select model, problems, cost_pence, coalesce(job, 'draft') from attempts").fetchall()
            # each draft once, as last approved: a log from before kept every approval
            approved, edited = self.db.execute(
                "select count(*), coalesce(sum(edited), 0) from approvals"
                " where id in (select max(id) from approvals group by draft_id)").fetchone()
        models, wrote = {}, {}
        for model, problems, cost, job in rows:
            use = models.setdefault(model, {"model": model, "attempts": 0, "passed": 0, "cost_pence": Decimal(0)})
            use["attempts"] += 1
            use["passed"] += problems == "[]"
            use["cost_pence"] += pence(cost)
            wrote[model] = wrote.get(model, 0) + (problems == "[]" and job != "colour")
        passed = sum(wrote.values())
        local = sum(n for model, n in wrote.items() if not model.startswith("claude"))
        drafts, cost = sum(ended.values()), sum(m["cost_pence"] for m in models.values())
        return {"drafts": drafts, "ready": ended.get("ready", 0), "needs_you": ended.get("needs you", 0),
                "done_on_this_mac": round(local / passed, 3) if passed else 0.0,
                "models": [{**m, "cost_pence": float(round(m["cost_pence"], 4))} for m in models.values()],
                "cost_pence": float(round(cost, 4)),
                "cost_per_100_drafts_pence": float(round(100 * cost / drafts, 4)) if drafts else 0.0,
                "approved": approved, "edited_before_sending": edited}
