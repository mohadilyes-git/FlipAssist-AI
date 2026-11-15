"""The command lines, python -m flip.draft and python -m flip.message, with pretend drafting: nothing is read from
Ollama, nothing is sent anywhere, and the audit log and your style are left alone."""

import json
import sys

import pytest

from flip import draft, message


@pytest.fixture(params=[(None, "claude-sonnet-5-5"), ("claude-opus-5-5", "claude-opus-5-5")])
def backup(request, monkeypatch):
    """With an Anthropic key: the paid backup's name, as FLIP_BACKUP_MODEL sets it (Claude Sonnet 5.5 when unset)."""
    named, expected = request.param
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    if named:
        monkeypatch.setenv("FLIP_BACKUP_MODEL", named)
    else:
        monkeypatch.delenv("FLIP_BACKUP_MODEL", raising=False)
    return expected


def test_flip_draft_falls_back_to_the_apps_paid_backup(backup, monkeypatch, tmp_path):
    """15 Nov review: it built Claude Haiku 5.5, so its fallback and colour look weren't Sonnet's, as the README says."""
    items = tmp_path / "items.json"
    items.write_text(json.dumps([{"id": "t1", "original_title": "iPhone 13 128GB", "my_notes": "Small scratch"}]))
    used = []

    def drafted(entry, catalogue, conditions, local, api, mode, photos, log):
        used.append(api)
        return {"item_id": entry["id"], "status": "needs you", "attempts": []}

    monkeypatch.setattr(draft, "draft_listing", drafted)
    monkeypatch.setattr(draft, "show", lambda result, problems: None)
    monkeypatch.setattr(draft, "AuditLog", lambda: None)
    monkeypatch.setattr(sys, "argv", ["flip.draft", str(items)])
    draft.main()
    assert [api.name for api in used] == [backup]


def test_flip_message_falls_back_to_the_apps_paid_backup(backup, monkeypatch):
    """The same for a message: its reading and its drafting fall back to the paid backup, as in the app."""
    used = {}

    class Book:
        index = None

        def __init__(self, *args, **kwargs):
            pass

        def card(self):
            return {}

    def read(listing, local, api, mode, log):
        used["read"] = api
        return {"flaws": [], "pickup": "", "no_offers": "", "read_by": "code", "attempts": [], "reasons": []}

    def drafted(listing, card, index, local, api, *args, **kwargs):
        used["draft"] = api
        return {"status": "needs you", "kind": "lower", "offer": 18700, "examples": [], "answer": None, "note": None,
                "words": None, "point": [], "ask": None, "reasons": [], "attempts": []}

    for name, fake in (("StyleBook", Book), ("MessageIndex", lambda: None), ("reader_for", lambda local: local),
                       ("read_listing_with_ai", read), ("draft_message", drafted), ("AuditLog", lambda: None)):
        monkeypatch.setattr(message, name, fake)
    monkeypatch.setattr(sys, "argv", ["flip.message", "iPhone 13 128GB", "--asking", "220"])
    message.main()
    assert (used["read"].name, used["draft"].name) == (backup, backup)
