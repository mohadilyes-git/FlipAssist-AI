"""FlipAssist's API: what AlertFlip calls to draft listings and offer messages.

    .venv/bin/uvicorn flip.api:app --port 8000
    then open http://127.0.0.1:8000/docs: every endpoint, what it takes and what it answers

It runs on this Mac only (127.0.0.1) unless it's put online on purpose, and
every endpoint but /health needs the key from .env (FLIP_API_KEY) in an
X-API-Key header. AlertFlip calls it from a Supabase function, so the key
stays on a server, never inside the phone app.

FlipAssist only drafts. It never sends a message or lists anything: AlertFlip
does that once you approve, and /drafts/{id}/approve records what you actually
sent, edited or not, so the results can count how often a draft was right as
it was. A message you approve also joins the messages your style is learned
from (/style), with the ones you wrote or pasted when setting it up. /stats is
the cost meter.
"""

import hmac
import os
import re
import subprocess
import tempfile
import urllib.request
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from flip.ai import ApiModel, LocalModel
from flip.audit import AuditLog
from flip.catalogue import load_catalogue, load_conditions
from flip.draft import load_env
from flip.drafter import draft_listing
from flip.message_drafter import MESSAGE_TOKENS, draft_message
from flip.money import to_pence
from flip.photos import photo_base64
from flip.prompts import offer_words
from flip.reader import read_listing_with_ai
from flip.retrieval import MessageIndex
from flip.style import StyleBook, phrase_rows, traits

MAX_PHOTOS = 8
MAX_PHOTO_BYTES = 15 * 1024 * 1024  # an iPhone photo is 2-5 MB
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
MONEY = r"^\d{1,6}(?:\.\d{1,2})?$"  # pounds, as written: "220" or "219.99"
Mode = Literal["auto", "local", "api"]

load_env()  # FLIP_API_KEY and ANTHROPIC_API_KEY, from .env; nothing already set is overwritten


# ── what goes in and what comes out ─────────────────────────────────────────

class Listing(BaseModel):
    """A seller's listing, as AlertFlip found it."""
    title: str = Field(min_length=1, max_length=300)
    description: str = Field("", max_length=5000)
    asking_price: str = Field(pattern=MONEY, description='pounds, as written: "220" or "219.99"')
    marketplace: str = Field("", max_length=40, description="facebook, ebay, vinted, gumtree...")
    id: str | None = Field(None, max_length=100, description="AlertFlip's own id for it, kept in the audit log")


class MessageRequest(BaseModel):
    listing: Listing
    kind: Literal["lower", "asking", "more"] = "lower"
    mention: bool | None = Field(None, description="say the listing's flaw or good condition; null: your style decides")
    length: Literal["usual", "longer"] = "usual"
    previous: str | None = Field(None, max_length=1000, description="the draft on screen, to make longer")
    writer: Literal["auto", "template", "ai"] = Field("auto", description="auto: your past messages decide")
    offer: str | None = Field(None, pattern=MONEY, description="the price you picked, in pounds; leave it out and code "
                                                                "starts from its own (15% under, or 5% over, asking)")
    mode: Mode = "auto"


class Attempt(BaseModel):
    model: str
    problems: list[str]
    seconds: float
    cost_pence: float


class Reading(BaseModel):
    """What was read from the listing, in the seller's own words."""
    flaws: list[str]
    pickup: str
    no_offers: str
    read_by: str
    attempts: list[Attempt]


class MessageDraft(BaseModel):
    draft_id: int
    status: Literal["ready", "needs you"]
    message: str | None
    written_by: str | None = Field(description="template (no AI), gemma3:4b or claude-haiku-5-5")
    kind: str
    offer: str = Field(description='the price code set, as said in the message: "£185"')
    offer_pence: int
    note: str | None = Field(description="to show under the message, e.g. the seller's own \"no offers\" words")
    ask: str | None = Field(description="a question for you, e.g. whether to mention the listing's flaw")
    point: list[str] = Field(description="what the listing gives this offer to say, in the seller's words")
    mentioned: bool
    questions: list[str]
    reading: Reading
    reasons: list[str] = Field(description="why it needs you, if it does")
    attempts: list[Attempt]
    cost_pence: float = Field(description="reading and drafting together")


class ListingDraft(BaseModel):
    draft_id: int
    status: Literal["ready", "needs you"]
    ebay_title: str | None
    condition_id: str | None
    condition_note: str | None
    description: str | None
    colour: str | None
    filled_by_code: dict = Field(description="model, storage, network, specs...: from the catalogue, no AI")
    warnings: list[str]
    reasons: list[str]
    photo_count: int
    attempts: list[Attempt]
    cost_pence: float


class Approval(BaseModel):
    sent: str = Field(min_length=1, max_length=5000,
                      description="what you actually sent (a message) or listed (a description), as you sent it")


class Approved(BaseModel):
    draft_id: int
    edited: bool
    at: str
    saved_to_style: bool = Field(description="a message you approve joins the messages your style is learned from")


class Row(BaseModel):
    k: str
    v: str


class Style(BaseModel):
    """What it learned from your messages, with plain code: nothing gets trained."""
    count: int = Field(description="how many of your messages it learns from")
    traits: list[Row] = Field(description="the style card: habits in 40% or more of your messages")
    phrases: list[Row] = Field(description="the phrasebook: sentences in 2 or more of your messages, the price as …")


class NewMessage(BaseModel):
    """A message you've sent a seller, with the listing it was for."""
    title: str = Field("", max_length=300, description="the listing's title")
    price: str = Field("", max_length=20, description='its asking price, as written: "£220", "220", or empty')
    text: str = Field(min_length=1, max_length=2000, description="your message, as you sent it")
    marketplace: str = Field("", max_length=40)


class StyleMessage(BaseModel):
    id: str
    title: str
    price: str = Field(description='the asking price in pounds, as written: "220"; empty if not given')
    text: str
    marketplace: str
    source: str = Field(description="added (in the app), approved (a draft you sent) or csv (flip.message --learn)")
    at: str


class ModelUse(BaseModel):
    model: str
    attempts: int
    passed: int
    cost_pence: float


class Stats(BaseModel):
    drafts: int
    ready: int
    needs_you: int
    done_on_this_mac: float = Field(description="share of passing answers from the template or the local model")
    models: list[ModelUse]
    cost_pence: float
    cost_per_100_drafts_pence: float
    approved: int
    edited_before_sending: int


class Health(BaseModel):
    local_model: str
    local_running: bool
    api_model: str
    api_key_set: bool = Field(description="the Anthropic key for the paid fallback is in .env")
    flip_api_key_set: bool = Field(description="the key callers need is set; without it every call is refused")


# ── what every endpoint shares ──────────────────────────────────────────────

class Setup:
    """The models, the audit log and the catalogue: made once, on the first call that needs them."""

    def __init__(self, local, api, log, local_listing=None):
        self.local, self.api, self.log = local, api, log
        self.local_listing = local_listing or local  # listings get the bigger answer budget
        self.catalogue, self.conditions = load_catalogue(), load_conditions()


@lru_cache
def audit():
    return AuditLog()


@lru_cache
def setup():
    api = ApiModel() if os.environ.get("ANTHROPIC_API_KEY") else None
    return Setup(LocalModel(max_tokens=MESSAGE_TOKENS), api, audit(), LocalModel())


@lru_cache
def style():
    """Your messages, your style card from them, and the search for the closest."""
    return StyleBook(index=MessageIndex())


def key(x_api_key: str | None = Header(None, description="FLIP_API_KEY from .env")):
    """Every endpoint but /health: the caller must send the key."""
    expected = os.environ.get("FLIP_API_KEY", "")
    if not expected:
        raise HTTPException(503, "set FLIP_API_KEY in .env first: without it nobody can call this")
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(401, "missing or wrong X-API-Key")


def attempts(found):
    return [Attempt(model=a["model"], problems=a["problems"], seconds=round(a["seconds"], 2),
                    cost_pence=float(a["cost_pence"] or 0)) for a in found]


def new_id():
    return f"api-{uuid.uuid4().hex[:12]}"


def pounds(written):
    """"£1,200" -> "1200", "" -> ""; None if it isn't a price."""
    plain = re.sub(r"[£,\s]", "", written)
    return plain if not plain or re.fullmatch(MONEY, plain) else None


def shown(message):
    return StyleMessage(id=message["id"], title=message["listing_title"], price=message["asking_price"],
                        text=message["my_message"], marketplace=message["marketplace"], source=message["source"],
                        at=message["at"])


# ── the endpoints ───────────────────────────────────────────────────────────

app = FastAPI(title="FlipAssist", version="0.4.0",
              description="Drafts eBay listings and offer messages. Code does what it can, a local AI the rest, a "
                          "paid AI only when the local answer fails a check, and a person approves every draft.")


@app.get("/health", response_model=Health)
def health():
    """Whether the local model is running and the keys are set. No key needed, and no key shown."""
    local = LocalModel()
    try:
        with urllib.request.urlopen(f"{local.url}/api/tags", timeout=2) as answer:
            running = answer.status == 200
    except OSError:
        running = False
    return Health(local_model=local.name, local_running=running, api_model=ApiModel().name,
                  api_key_set=bool(os.environ.get("ANTHROPIC_API_KEY")),
                  flip_api_key_set=bool(os.environ.get("FLIP_API_KEY")))


@app.post("/messages/draft", response_model=MessageDraft, dependencies=[Depends(key)])
def draft_a_message(request: MessageRequest, s: Setup = Depends(setup), book: StyleBook = Depends(style)):
    """Read the listing (its flaws, where to collect, whether the seller takes
    offers), then draft the offer: code sets the price, your own sentences
    or the AI write it, and the checks decide."""
    listing = {**request.listing.model_dump(), "id": request.listing.id or new_id()}
    reading = read_listing_with_ai(listing, s.local, s.api, request.mode, s.log)
    try:
        result = draft_message(listing, book.card(), book.index, s.local, s.api, request.mode, s.log, kind=request.kind,
                               mention=request.mention, length=request.length, previous=request.previous,
                               reading=reading, writer=request.writer,
                               offer=to_pence(request.offer) if request.offer else None)
    except ValueError as e:
        raise HTTPException(422, str(e))
    answer = result["answer"] or {}
    tried = attempts(result["attempts"])
    read = attempts(reading["attempts"])
    return MessageDraft(
        draft_id=result["draft_id"], status=result["status"], message=answer.get("message"),
        written_by=result["writer"], kind=result["kind"], offer=offer_words(result["offer"]),
        offer_pence=result["offer"], note=result["note"], ask=result["ask"], point=result["point"],
        mentioned=result["mentioned"], questions=result["questions"],
        reading=Reading(flaws=reading["flaws"], pickup=reading["pickup"], no_offers=reading["no_offers"],
                        read_by=reading["read_by"], attempts=read),
        reasons=result["reasons"], attempts=tried, cost_pence=round(sum(a.cost_pence for a in tried + read), 4))


@app.post("/listings/draft", response_model=ListingDraft, dependencies=[Depends(key)])
def draft_a_listing(title: str = Form(min_length=1, max_length=300), description: str = Form("", max_length=5000),
                    notes: str = Form("", max_length=2000, description="your notes from looking at the item"),
                    id: str | None = Form(None, max_length=100), mode: Mode = Form("auto"),
                    photos: list[UploadFile] = File(default=[], description=f"up to {MAX_PHOTOS} photos"),
                    s: Setup = Depends(setup)):
    """Draft an eBay listing: code fills what the catalogue knows, the AI the
    colour (from the photos), the condition and the description, and the
    checks hold it to your notes."""
    if len(photos) > MAX_PHOTOS:
        raise HTTPException(422, f"at most {MAX_PHOTOS} photos")
    encoded = []
    with tempfile.TemporaryDirectory() as folder:
        for n, photo in enumerate(photos):
            suffix = Path(photo.filename or "").suffix.lower()
            if suffix not in PHOTO_TYPES:
                raise HTTPException(422, f"{photo.filename}: send photos as JPEG, PNG, HEIC or WebP")
            data = photo.file.read(MAX_PHOTO_BYTES + 1)
            if len(data) > MAX_PHOTO_BYTES:
                raise HTTPException(413, f"{photo.filename}: bigger than {MAX_PHOTO_BYTES // 1024 // 1024} MB")
            path = Path(folder) / f"photo-{n}{suffix}"
            path.write_bytes(data)
            try:
                encoded.append(photo_base64(path))
            except (OSError, ValueError, subprocess.CalledProcessError):
                raise HTTPException(422, f"{photo.filename}: can't be read as a photo")
    entry = {"id": id or new_id(), "original_title": title, "original_description": description, "my_notes": notes}
    result = draft_listing(entry, s.catalogue, s.conditions, s.local_listing, s.api, mode, encoded, s.log)
    answer, item = result["answer"] or {}, result["item"]
    tried = attempts(result["attempts"])
    return ListingDraft(
        draft_id=result["draft_id"], status=result["status"], ebay_title=result["title"],
        condition_id=answer.get("condition_id"), condition_note=answer.get("condition_note"),
        description=answer.get("description"), colour=answer.get("colour") or item.get("colour"),
        filled_by_code={k: v for k, v in item.items() if k not in ("warnings", "missing")},
        warnings=result["warnings"], reasons=result["reasons"], photo_count=len(encoded), attempts=tried,
        cost_pence=round(sum(a.cost_pence for a in tried), 4))


@app.post("/drafts/{draft_id}/approve", response_model=Approved, dependencies=[Depends(key)])
def approve(draft_id: int, approval: Approval, log: AuditLog = Depends(audit), book: StyleBook = Depends(style)):
    """Record what you actually sent for a draft, and whether you edited it. A
    message also joins the messages your style is learned from, once however
    often it's approved."""
    found = log.approve(draft_id, approval.sent)
    if found is None:
        raise HTTPException(404, "no draft with that id")
    listing = log.listing(draft_id)
    if listing is not None:
        book.add([{"id": f"draft-{draft_id}", "listing_title": listing["title"], "asking_price": listing["asking_price"],
                   "marketplace": listing["marketplace"], "my_message": approval.sent}], "approved")
    return {**found, "saved_to_style": listing is not None}


@app.get("/style", response_model=Style, dependencies=[Depends(key)])
def your_style(book: StyleBook = Depends(style)):
    """What it learned from your messages: the style card (habits in 40% or
    more of them) and the phrasebook (sentences in 2 or more). Plain code."""
    card = book.card()
    return Style(count=card.get("messages", 0), traits=[Row(k=k, v=v) for k, v in traits(card)],
                 phrases=[Row(k=k, v=v) for k, v in phrase_rows(card)])


@app.get("/style/messages", response_model=list[StyleMessage], dependencies=[Depends(key)])
def style_messages(book: StyleBook = Depends(style)):
    """The messages your style is learned from, newest first."""
    return [shown(m) for m in book.messages()]


@app.post("/style/messages", response_model=list[StyleMessage], status_code=201, dependencies=[Depends(key)])
def add_style_messages(messages: list[NewMessage] = Body(min_length=1, max_length=100),
                       book: StyleBook = Depends(style)):
    """Add messages you've sent sellers. The next draft already learns from them."""
    rows = []
    for m in messages:
        price = pounds(m.price)
        if price is None:
            raise HTTPException(422, f"{m.price}: not a price")
        if not m.text.strip():
            raise HTTPException(422, "a message needs some words")
        rows.append({"listing_title": m.title.strip(), "asking_price": price, "marketplace": m.marketplace.strip(),
                     "my_message": m.text})
    return [shown(m) for m in book.add(rows, "added")]


@app.delete("/style/messages/{message_id}", status_code=204, dependencies=[Depends(key)])
def forget_style_message(message_id: str, book: StyleBook = Depends(style)):
    """Stop learning from one of your messages."""
    if not book.remove(message_id):
        raise HTTPException(404, "no message with that id")


@app.get("/stats", response_model=Stats, dependencies=[Depends(key)])
def stats(log: AuditLog = Depends(audit)):
    """The cost meter: drafts, who did the work, what it cost, how often you edited."""
    return log.stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("flip.api:app", host="127.0.0.1", port=8000)
