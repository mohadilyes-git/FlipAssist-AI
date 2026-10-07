"""FlipAssist's API: what AlertFlip calls to draft listings and offer messages.

    .venv/bin/uvicorn flip.api:app --port 8000
    then open http://127.0.0.1:8000/docs: every endpoint, what it takes and what it answers

It runs on this Mac only (127.0.0.1) unless it's put online on purpose, and
every endpoint but /health (and the /docs pages, which only describe them)
needs the key from .env (FLIP_API_KEY) in an X-API-Key header. A request
without it, or bigger than its endpoint takes, is turned away before any of
it is read (Gate). AlertFlip calls it from a Supabase function, so the key
stays on a server, never inside the phone app.

FlipAssist only drafts. It never sends a message or lists anything: AlertFlip
does that once you approve, and /drafts/{id}/approve records what you actually
sent, edited or not, so the results can count how often a draft was right as
it was. A message you approve also joins the messages your style is learned
from (/style), with the ones you wrote or pasted when setting it up. /stats is
the cost meter.
"""

import hmac
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi import Path as PathParam
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from flip.ai import ApiModel, LocalModel, whole_text
from flip.audit import AuditLog
from flip.catalogue import load_catalogue, load_conditions
from flip.draft import load_env
from flip.kinds import model_name as kinds_model, sorter as kinds_sorter
from flip.prices import estimate, kind_of, settings as prices_settings
from flip.drafter import draft_listing
from flip.message_drafter import MESSAGE_TOKENS, Refused, draft_message, offer_to_draft
from flip.offers import check_battery_reason, check_condition_talk
from flip.style_ai import MODEL as STYLE_MODEL
from flip.wording import MODEL as WORDING_MODEL, check_reason, completed, settings
from flip.money import to_pence
from flip.photos import NotAPhoto, photo_base64, photo_kind
from flip.prompts import offer_words
from flip.reader import read_listing_with_ai, reader_for, reader_name
from flip.retrieval import MessageIndex
from flip.style import StyleBook, phrase_rows, traits

MAX_PHOTOS = 8
MAX_PHOTO_BYTES = 15 * 1024 * 1024  # an iPhone photo is 2-5 MB
MAX_JSON = 1024 * 1024  # a message request is a few KB; 100 messages for your style fit with room to spare
MAX_FORM = MAX_PHOTOS * MAX_PHOTO_BYTES + MAX_JSON  # /listings/draft: 8 photos and the text
MIN_KEY = 32  # characters: the placeholder from .env.example, or anything short, is as good as no key
MAX_ID = 2**63 - 1  # the biggest id SQLite keeps
OPEN = {"/health", "/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}  # no key: they call nothing
MONEY = r"^\d{1,6}(?:\.\d{1,2})?$"  # pounds, as written: "220" or "219.99"
Mode = Literal["auto", "local", "api"]

load_env()  # FLIP_API_KEY and ANTHROPIC_API_KEY, from .env; nothing already set is overwritten


# ── what goes in and what comes out ─────────────────────────────────────────

class Listing(BaseModel):
    """A seller's listing, as AlertFlip found it."""
    title: str = Field(min_length=1, max_length=300)
    description: str = Field("", max_length=5000)
    asking_price: str = Field(pattern=MONEY, description='pounds, as written: "220" or "219.99"; £1 or more')
    marketplace: str = Field("", max_length=40, description="facebook, ebay, vinted, gumtree...")
    id: str | None = Field(None, max_length=100, description="AlertFlip's own id for it, kept in the audit log")


class Reason(BaseModel):
    clause: str = Field(description="the reason after \"I'm offering that because\", as the message gives it")
    by: str = Field(description="who worded it: FlipAssist's wording model (flip-wording-4b since 6 Oct), or "
                             "claude-sonnet-5-5 when Sonnet fixed it")
    checked: str = Field(description='"ok" (Haiku passed it), "fixed" (Sonnet), "flagged, kept", "not checked"')


class ReasonOnScreen(BaseModel):
    """The reason the message on screen gives, sent back with Make it longer and Rewrite: kept as it is, not worded
    and checked again (it may be Sonnet's fix, which flip-wording would only word again the old way)."""
    clause: str = Field(min_length=1, max_length=500)
    by: str = Field(max_length=100)
    checked: str = Field(max_length=40)
    quotes: list[str] = Field(default_factory=list, max_length=50, description="reading.quotes of that draft: the "
                              "reason is kept only when the listing still reads as these same lines")


class MessageRequest(BaseModel):
    listing: Listing
    kind: Literal["lower", "asking", "more"] = "lower"
    mention: bool | None = Field(None, description="say the listing's flaw or good condition; null: your style decides")
    length: Literal["usual", "longer"] = "usual"
    previous: str | None = Field(None, max_length=1000, description='the draft on screen, to make longer: only with '
                                                                    '"length": "longer"')
    writer: Literal["auto", "template", "ai"] = Field("auto", description="auto: your own sentences first, the AI "
                                                        "only when they can't say it")
    rewrite_of: str | None = Field(None, max_length=5000, description="the message on screen, for Rewrite: the new "
                                                                      "one says it in other words")
    offer: str | None = Field(None, pattern=MONEY, description="the price you picked, in pounds; leave it out and code "
                                                                "starts from its own (15% under, or 5% over, asking)")
    mode: Mode = "auto"
    check_later: bool = Field(False, description="the app's way: the reason flip-wording wrote comes back straight "
                                                 "away (reason.checked \"pending\"), and /messages/check-reason "
                                                 "checks it after the draft is on screen")
    reason: ReasonOnScreen | None = Field(None, description="with previous or rewrite_of: the reason the message on "
                                                            "screen gives (draft.reason), kept when that message still "
                                                            "says it")


class ReasonCheckRequest(BaseModel):
    """A drafted message whose reason is "pending": the draft's own listing, flaws, reason and message."""
    draft_id: int = Field(ge=1, le=10**9)
    listing: Listing
    flaws: list[str] = Field(max_length=50, description="reading.flaws from the draft: the code checks' flaws")
    quotes: list[str] = Field(default_factory=list, max_length=50, description="reading.quotes from the draft: the "
                              "sentences flip-wording worded the reason from, which Haiku checks it against (the "
                              "flaws when empty)")
    clause: str = Field(min_length=1, max_length=500, description="reason.clause from the draft")
    message: str = Field(min_length=1, max_length=5000, description="the message as drafted")
    kind: Literal["lower", "asking", "more"] = "lower"
    offer_pence: int = Field(ge=100, le=10**9)
    by: str | None = Field(None, max_length=100, description="reason.by from the draft: the model that worded the "
                                                             "clause, credited when the check keeps it (6 Oct review)")


class Attempt(BaseModel):
    model: str
    problems: list[str]
    seconds: float
    cost_pence: float
    colour_only: bool = Field(False, description="a second look at the colour alone, not a draft")
    job: str = Field("draft", description='"reason" for the steps that word the reason (flip-wording, Haiku, Sonnet)')


class Reading(BaseModel):
    """What was read from the listing, in the seller's own words."""
    flaws: list[str]
    quotes: list[str] = Field(default_factory=list, description="the reader's whole sentences the reason is worded "
                              "from: FlipAssist's reader's quotes before code cuts a seller's story off (flaws), "
                              "else the flaws")
    pickup: str
    no_offers: str
    read_by: str
    attempts: list[Attempt]


class ReasonCheck(BaseModel):
    reason: Reason
    message: str = Field(description="the message with the fixed reason in it, or as it was")
    changed: bool = Field(description="the message changed: show this one, unless you've already edited yours")
    problems: list[str] = Field(description="why a fix wasn't put in the message, if one wasn't")
    attempts: list[Attempt]
    cost_pence: float


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
    warnings: list[str] = Field(description="worth knowing before you send: a title and description that name "
                                            "different models, a rewrite that couldn't find other words")
    attempts: list[Attempt]
    reason: Reason | None = Field(None, description="the reason flip.wording worded and checked, when it did")
    cost_pence: float = Field(description="reading and drafting together")


class EbayCategory(BaseModel):
    id: str = Field(description="eBay UK's category id: 9355 for Mobile & Smart Phones")
    name: str
    path: str = Field(description="the categories above it, as eBay shows them")


class ItemSpecific(BaseModel):
    name: str = Field(description="eBay's name for the field: Brand, Model, Storage Capacity...")
    value: str | None = Field(description="in eBay's own words; null when nobody knows it")
    required: bool = Field(description="eBay won't list without it")
    source: str | None = Field(description="the catalogue, your title or notes, or the photos (with the exact colour)")
    options: list[str] = Field(description="eBay's values to pick from")
    hint: str | None = Field(None, description="for an empty field, what the seller's description says, to check")


class ListingDraft(BaseModel):
    draft_id: int
    status: Literal["ready", "needs you"]
    ebay_title: str | None
    condition_id: str | None
    condition_note: str | None
    description: str | None
    colour: str | None = Field(description="one of the model's colours, checked; null when neither the listing nor "
                                           "the photos settle it")
    colour_from: Literal["listing", "photos"] | None = Field(
        description="listing: code read it from the title, description or notes; photos: the AI picked it from them")
    colour_by: str | None = Field(None, description="the model that picked the colour from the photos: the local "
                                                    "model, or the paid one when the local one was unsure")
    filled_by_code: dict = Field(description="model, storage, network, specs...: from the catalogue, no AI")
    ebay_category: EbayCategory | None = Field(description="eBay UK's category; phones so far")
    item_specifics: list[ItemSpecific] = Field(description="eBay's fields filled by code, in eBay's order and words")
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


class Learned(BaseModel):
    """One thing your style puts in a message, yours to keep or remove."""
    key: str = Field(description="what to send to /style/learned to remove it or put it back")
    what: str = Field(description='"Opens with", "Mentions", "Says the flaw", "Emojis", "Usual opener", "Offer '
                                  'sentence", "Offer under asking", "Offer at asking", "Offer over asking", '
                                  '"Closing" or "Asks every time"')
    value: str = Field(description="the greeting, habit, sentence or question, the price as …")
    used: bool = Field(description="false once you've removed it: then no draft writes it")


class Style(BaseModel):
    """What it learned from your messages, with plain code: nothing gets trained."""
    count: int = Field(description="how many of your messages it learns from")
    traits: list[Row] = Field(description="the style card: habits in 40% or more of your messages")
    phrases: list[Row] = Field(description="the phrasebook: sentences in 2 or more of your messages, the price as …")
    learned: list[Learned] = Field(default=[], description="everything it puts in a message, removed ones included")


class LearnedUse(BaseModel):
    """Keep or remove one thing your style learned."""
    key: str = Field(min_length=1, max_length=2100, description="its key, from /style")
    used: bool = Field(description="false to remove it, true to put it back")


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
    job: str = Field("draft", description='"read", "draft" (writing), "reason" or "colour"')
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


class ModelState(BaseModel):
    job: str = Field(description='"reads listings", "words the reason", "sorts price flaws", "reads your style" or '
                                 '"writes messages"')
    name: str = Field(description="the model's name in Ollama")
    installed: bool = Field(description="this Mac's Ollama has it; when it doesn't, code (or Gemma) does that job")


class Health(BaseModel):
    local_model: str
    local_running: bool
    api_model: str
    api_key_set: bool = Field(description="the Anthropic key for the paid fallback is in .env")
    flip_api_key_set: bool = Field(description=f"the key callers need is set, {MIN_KEY} characters or more; "
                                                "without it every call is refused")
    models: list[ModelState] = Field(default_factory=list, description="the models Ollama is asked for, by job, and "
                                     "whether it has each (empty when Ollama isn't running; a job turned off in .env "
                                     "isn't listed)")


# ── what every endpoint shares ──────────────────────────────────────────────

class Setup:
    """The models, the audit log and the catalogue: made once, on the first call that needs them."""

    def __init__(self, local, api, log, local_listing=None, reader=None, wording=None, kinds=None):
        self.local, self.api, self.log = local, api, log
        self.kinds = kinds  # what sorts a price's flaws: a sorter, or a function that gives one (None: code sorts)
        self.wording = wording  # the reason's models (flip.wording): "settings" in the app, None (off) unless given
        self.local_listing = local_listing or local  # listings get the bigger answer budget
        self.reader = reader  # what reads the seller's listing: a model, or a function that gives one when asked
        self.catalogue, self.conditions = load_catalogue(), load_conditions()

    def reading_model(self):
        """The model that reads the seller's listing: FlipAssist's own reader
        when Ollama has it (looked up at each reading, so one installed or
        started later is used), else the local model that writes."""
        found = self.reader() if callable(self.reader) else self.reader
        return found or self.local

    def flaw_sorter(self):
        """What sorts a price's flaws into the API's kinds: flip-kinds when Ollama has it (looked up at each price
        check), else None, and code's rules sort them (flip.kinds)."""
        if self.kinds is None or hasattr(self.kinds, "name"):
            return self.kinds
        return self.kinds()


@lru_cache
def audit():
    return AuditLog()


@lru_cache
def setup():
    api = ApiModel() if os.environ.get("ANTHROPIC_API_KEY") else None
    local = LocalModel(max_tokens=MESSAGE_TOKENS)
    return Setup(local, api, audit(), LocalModel(), reader=lambda: reader_for(local), wording="settings",
                 kinds=lambda: kinds_sorter(local.url))


@lru_cache
def style():
    """Your messages, your style card from them, and the search for the closest."""
    # our AI (flip-style-1b, FlipAssist's style reader, on this Mac; plain Gemma before 6 Oct) reads your messages too
    # when they change (flip.style_ai); the drafts use only what code checks in them. FLIP_STYLE_AI= (empty) in .env
    # leaves your style to code alone; FLIP_STYLE_AI=gemma3:4b goes back to plain Gemma
    name = style_model()
    return StyleBook(index=MessageIndex(), ai=LocalModel(name, timeout=180, max_tokens=700) if name else None)


def style_model():
    """The style reader's name: FLIP_STYLE_AI from the environment or .env, flip-style-1b when it isn't set; "" = off."""
    return os.environ.get("FLIP_STYLE_AI", STYLE_MODEL).strip()


def usable_key():
    """FLIP_API_KEY, or "" when it's unset, the placeholder, or too short to be a key."""
    found = os.environ.get("FLIP_API_KEY", "").strip()
    return found if len(found) >= MIN_KEY else ""


def refusal(given):
    """Why a call sending this X-API-Key is turned away, as (status, words), or None."""
    expected = usable_key()
    if not expected:
        return 503, f"set FLIP_API_KEY in .env first, a random one of {MIN_KEY} characters or more (.env.example " \
                    "shows how): without it nobody can call this"
    if not given or not hmac.compare_digest(given.encode(), expected.encode()):
        return 401, "missing or wrong X-API-Key"
    return None


def key(x_api_key: str | None = Header(None, description="FLIP_API_KEY from .env")):
    """Every endpoint but /health: the caller must send the key. Gate has
    already checked it; this shows it in /docs, and checks it again."""
    refused = refusal(x_api_key)
    if refused:
        raise HTTPException(*refused)


class Gate:
    """Turns a request away before anything reads its body: one without the
    key (every path but OPEN's), and one bigger than its endpoint takes, by
    its Content-Length or, sent in chunks, as it arrives. FastAPI reads and
    parses a whole body before an endpoint's own checks run, so without this
    a caller with no key could make this Mac hold or write all they sent."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in OPEN:
            return await self.app(scope, receive, send)
        headers = Headers(scope=scope)
        limit = MAX_FORM if scope["path"] == "/listings/draft" else MAX_JSON
        too_big = 413, f"too big: at most {limit // 1024 // 1024} MB here"
        length = headers.get("content-length")
        refused = refusal(headers.get("x-api-key")) or (
            too_big if length is not None and (not length.isdigit() or int(length) > limit) else None)
        if refused:
            return await JSONResponse({"detail": refused[1]}, status_code=refused[0])(scope, receive, send)
        taken = 0

        async def counted():
            nonlocal taken
            message = await receive()
            taken += len(message.get("body", b""))
            if taken > limit:
                raise HTTPException(*too_big)  # FastAPI passes it on as the answer
            return message

        await self.app(scope, counted, send)


def attempts(found):
    return [Attempt(model=a["model"], problems=a["problems"], seconds=round(a["seconds"], 2),
                    cost_pence=float(a["cost_pence"] or 0), colour_only=a.get("colour_only", False),
                    job=a.get("job", "draft")) for a in found]


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


class WholeText(Request):
    """JSON can spell half a character ("\\ud800"). Python takes it, but the
    answer, the audit log and your style can't be written with it in, so a
    listing or message carrying one was a 500. It's made "\ufffd" before any
    endpoint sees the request."""

    async def json(self):
        if not hasattr(self, "_json"):
            self._json = whole_text(json.loads(await self.body()))
        return self._json


class WholeTextRoute(APIRoute):
    def get_route_handler(self):
        handle = super().get_route_handler()

        async def with_whole_text(request):
            return await handle(WholeText(request.scope, request.receive))
        return with_whole_text


# ── the endpoints ───────────────────────────────────────────────────────────

app = FastAPI(title="FlipAssist", version="0.4.0",
              description="Drafts eBay listings and offer messages. Code does what it can, a local AI the rest, a "
                          "paid AI only when the local answer fails a check, and a person approves every draft.")
app.add_middleware(Gate)
app.router.route_class = WholeTextRoute


@app.get("/health", response_model=Health)
def health():
    """Whether the local model is running and the keys are set. No key needed, and no key shown."""
    local = LocalModel()
    running, names = False, set()
    try:
        with urllib.request.urlopen(f"{local.url}/api/tags", timeout=2) as answer:
            running = answer.status == 200
            listed = json.load(answer).get("models") or []
            names = {m["name"] for m in listed if isinstance(m, dict) and isinstance(m.get("name"), str)}
    except (OSError, ValueError, AttributeError):
        pass
    # each model by its job, so a missing one shows (6 Oct review: Home said they were all running when Ollama was)
    wanted = [("reads listings", reader_name()), ("words the reason", settings()["wording"]),
              ("sorts price flaws", kinds_model()), ("reads your style", style_model()), ("writes messages", local.name)]
    models = [ModelState(job=job, name=name, installed=name in names or f"{name}:latest" in names)
              for job, name in wanted if name] if running else []
    return Health(local_model=local.name, local_running=running, api_model=ApiModel().name,
                  api_key_set=bool(os.environ.get("ANTHROPIC_API_KEY")),
                  flip_api_key_set=bool(usable_key()), models=models)


@app.post("/messages/draft", response_model=MessageDraft, dependencies=[Depends(key)])
def draft_a_message(request: MessageRequest, s: Setup = Depends(setup), book: StyleBook = Depends(style)):
    """Read the listing (its flaws, where to collect, whether the seller takes
    offers), then draft the offer: code sets the price, your own sentences
    or the AI write it, and the checks decide."""
    offer = to_pence(request.offer) if request.offer else None
    try:  # refused before anything runs: no reading, no model
        offer_to_draft(request.kind, to_pence(request.listing.asking_price), offer)
        if request.previous and request.length != "longer":
            raise Refused('previous is the draft to make longer: send it with "length": "longer"')
    except Refused as e:
        raise HTTPException(422, str(e))
    listing = {**request.listing.model_dump(), "id": request.listing.id or new_id()}
    reading = read_listing_with_ai(listing, s.reading_model(), s.api, request.mode, s.log)
    try:
        result = draft_message(listing, book.card(), book.index, s.local, s.api, request.mode, s.log, kind=request.kind,
                               mention=request.mention, length=request.length, previous=request.previous,
                               reading=reading, writer=request.writer, offer=offer, rewrite_of=request.rewrite_of,
                               wording=s.wording,  # flip-wording, Haiku's check, Sonnet's fix (flip.wording)
                               check_reason_now=not request.check_later,
                               reason_on_screen=request.reason.model_dump() if request.reason else None)
    except Refused as e:  # anything else is a fault here, not the caller's: a 500
        raise HTTPException(422, str(e))
    answer = result["answer"] or {}
    tried = attempts(result["attempts"])
    read = attempts(reading["attempts"])
    return MessageDraft(
        draft_id=result["draft_id"], status=result["status"], message=answer.get("message"),
        written_by=result["writer"], kind=result["kind"], offer=offer_words(result["offer"]),
        offer_pence=result["offer"], note=result["note"], ask=result["ask"], point=result["point"],
        mentioned=result["mentioned"], questions=result["questions"],
        reading=Reading(flaws=reading["flaws"], quotes=reading.get("quotes") or reading["flaws"],
                        pickup=reading["pickup"], no_offers=reading["no_offers"],
                        read_by=reading["read_by"], attempts=read),
        reasons=result["reasons"], warnings=result["warnings"], attempts=tried,
        reason=Reason(**result["reason"]) if result.get("reason") else None,
        cost_pence=round(sum(a.cost_pence for a in tried + read), 4))


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
            name = photo.filename or f"photo {n + 1}"
            data = photo.file.read(MAX_PHOTO_BYTES + 1)
            if len(data) > MAX_PHOTO_BYTES:
                raise HTTPException(413, f"{name}: bigger than {MAX_PHOTO_BYTES // 1024 // 1024} MB")
            kind = photo_kind(data[:16])  # by its bytes, whatever it's called: a Blob arrives as "blob"
            if kind is None:
                raise HTTPException(422, f"{name}: send photos as JPEG, PNG, HEIC or WebP")
            path = Path(folder) / f"photo-{n}{kind}"
            path.write_bytes(data)
            try:
                encoded.append(photo_base64(path))
            except NotAPhoto as e:  # more pixels than a photo has, or too slow to read
                raise HTTPException(422, f"{name}: {e.why}")
            except (OSError, ValueError, subprocess.CalledProcessError):
                raise HTTPException(422, f"{name}: can't be read as a photo")
    entry = {"id": id or new_id(), "original_title": title, "original_description": description, "my_notes": notes}
    result = draft_listing(entry, s.catalogue, s.conditions, s.local_listing, s.api, mode, encoded, s.log)
    answer, item = result["answer"] or {}, result["item"]
    tried = attempts(result["attempts"])
    return ListingDraft(
        draft_id=result["draft_id"], status=result["status"], ebay_title=result["title"],
        condition_id=answer.get("condition_id"), condition_note=answer.get("condition_note"),
        description=answer.get("description"), colour=item.get("colour"),
        colour_from=result["colour_from"], colour_by=result["colour_by"],
        filled_by_code={k: v for k, v in item.items()  # code's facts only: a colour from the photos is the AI's
                        if k not in ("warnings", "missing") and not (k == "colour" and result["colour_from"] == "photos")},
        ebay_category=(result.get("ebay") or {}).get("category"),
        item_specifics=(result.get("ebay") or {}).get("specifics", []),
        warnings=result["warnings"], reasons=result["reasons"], photo_count=len(encoded), attempts=tried,
        cost_pence=round(sum(a.cost_pence for a in tried), 4))


class PriceRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(None, max_length=5000,
                                    description="the seller's description: read for its flaws (as a draft's reading is) "
                                                "when flaws aren't sent")
    flaws: list[str] | None = Field(None, max_length=30, description="the flaws to cut for, if already read")


class PriceEstimate(BaseModel):
    """The listing's UK price from the AlertFlip app's prices API (flip.prices): price is the one with its flaws cut,
    middle a clean one's, low to high the middle half of clean sales (the cheapest quarter left out); skipped or error
    when there's none."""
    price: float | None = None
    middle: float | None = None
    low: float | None = None
    high: float | None = None
    currency: str = "GBP"
    sales: int | None = None
    model: str | None = None  # the API's name for it ("iphone 13"); item instead when it searched by words
    item: str | None = None
    storage_gb: int | None = None  # the size it priced...
    ram_gb: int | None = None  # (a MacBook's memory)
    asked_storage_gb: int | None = None  # ...and the size the listing gives (None: it gives none)
    asked_ram_gb: int | None = None
    kind: str | None = None  # "iphone", "samsung" or "macbook"
    kinds: list[str] = []  # the kinds of flaw it was cut for ("damage", "fault"...)
    cuts: list[str] = []
    parts_price: bool = False  # priced at what for-parts ones sell for (locked, for parts)
    rough: bool = False
    exact: bool = False
    mode: str | None = None
    skipped: str | None = None
    error: str | None = None
    # the flaws it was cut for: the reader's sentences when the description was read here, and who read them
    flaws: list[str] = []
    read_by: str | None = None
    # who sorted the flaws into kinds: "flip-kinds-1", "code" (its rules), "flip-kinds-1 and code"; None: no flaws
    sorted_by: str | None = None


class PriceChecks:
    """The audit log for a price check's reading: kept as the job "price", so Home counts it as what it is, not as
    reading for a draft (its cost isn't a draft's)."""

    def __init__(self, log):
        self.log = log

    def attempt(self, item_id, reply, problems, cost, job="draft"):
        self.log.attempt(item_id, reply, problems, cost, job="price")


@app.post("/prices/estimate", response_model=PriceEstimate, dependencies=[Depends(key)])
def estimate_price(request: PriceRequest, s: Setup = Depends(setup)):
    """What this listing sells for in the UK with its flaws: iPhones, Samsung phones and MacBooks (4 Oct), from the same
    prices API as the AlertFlip app. Send the description and the listing is read for its flaws first, as for a draft
    (the AI UK price estimate tab); send flaws and they're used as they are."""
    if kind_of(request.title) is None or not all(prices_settings()):  # before any reading: nothing to price it
        return PriceEstimate(**estimate(request.title))
    flaws, read_by = request.flaws or [], None
    if request.flaws is None and request.description is not None:
        listing = {"id": new_id(), "title": request.title, "description": request.description}
        reading = read_listing_with_ai(listing, s.reading_model(), s.api, "auto",
                                     PriceChecks(s.log) if s.log is not None else None)
        flaws, read_by = reading.get("quotes") or reading["flaws"], reading["read_by"]
    found = estimate(request.title, flaws, description=request.description, sorter=s.flaw_sorter() if flaws else None)
    return PriceEstimate(**found, flaws=flaws, read_by=read_by)


@app.post("/messages/check-reason", response_model=ReasonCheck, dependencies=[Depends(key)])
def check_a_reason(request: ReasonCheckRequest, s: Setup = Depends(setup)):
    """Steps 4-5 for a draft made with check_later: Haiku checks the reason, and only a flagged one goes to Sonnet.
    A fixed reason replaces the old one in the message (the writer puts it in word for word), the condition checks
    run again, and the audit log keeps the new text, so approving it counts as unedited. Anything that can't be done
    leaves the message as it was."""
    result = {"item_id": request.listing.id, "attempts": []}
    flaws = completed(request.quotes or request.flaws, request.listing.description)  # as the draft gave flip-wording
    # the model that worded it, as the draft said; the settings' only when the app didn't send it
    worded_by = request.by or settings()["wording"] or WORDING_MODEL
    if s.wording is None:
        checked = {"clause": request.clause, "by": "", "checked": "not checked"}
    else:
        models = None if s.wording == "settings" else s.wording
        checked = check_reason(request.listing.title, flaws, request.clause, worded_by, models, result, s.log)
    message, problems = request.message, []
    if checked["checked"] == "fixed":
        new = checked["clause"]
        at = request.message.lower().find(request.clause.lower())
        if new == "none":
            problems.append("Sonnet says nothing here is a flaw: the message still gives the reason, for you to judge")
        elif at < 0:
            problems.append("the message words the reason its own way, so the fix wasn't put in")
        else:
            fixed = request.message[:at] + new + request.message[at + len(request.clause):]
            sources = f"{request.listing.title}. {request.listing.description}\n{new}"
            point = {"about": "flaw", "says": request.flaws, "worded": new}
            problems = check_condition_talk(fixed, sources, point, True, request.kind, request.offer_pence) + \
                check_battery_reason(fixed, point, request.offer_pence, sources, request.listing.title, request.kind)
            if not problems:
                message = fixed
                if s.log:
                    s.log.redrafted(request.draft_id, message)
        if message == request.message:  # the fix didn't go in: the message still gives flip-wording's flagged reason
            checked = {"clause": request.clause, "by": worded_by, "checked": "flagged, kept"}
    tried = attempts(result["attempts"])
    return ReasonCheck(reason=Reason(**checked), message=message, changed=message != request.message,
                       problems=problems, attempts=tried, cost_pence=round(sum(a.cost_pence for a in tried), 4))


@app.post("/drafts/{draft_id}/approve", response_model=Approved, dependencies=[Depends(key)])
def approve(approval: Approval, draft_id: int = PathParam(ge=1, le=MAX_ID), log: AuditLog = Depends(audit),
            book: StyleBook = Depends(style)):
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
        book.learn_later()
    return {**found, "saved_to_style": listing is not None}


@app.get("/style", response_model=Style, dependencies=[Depends(key)])
def your_style(book: StyleBook = Depends(style)):
    """What it learned from your messages: the style card (habits in 40% or
    more of them) and the phrasebook (sentences in 2 or more). Plain code, its gaps filled by what our AI found that
    code checked is in your messages; our AI reads them again in the background when they've changed."""
    book.learn_later()
    card = book.card()
    return Style(count=card.get("messages", 0), traits=[Row(k=k, v=v) for k, v in traits(card)],
                 phrases=[Row(k=k, v=v) for k, v in phrase_rows(card)],
                 learned=[Learned(**row) for row in book.learned()])


@app.post("/style/learned", response_model=Style, dependencies=[Depends(key)])
def use_learned(change: LearnedUse, book: StyleBook = Depends(style)):
    """Keep or remove one thing your style learned (a greeting, a habit such
    as paying cash, a sentence, a question you ask every time). A removed one
    is off your style card, the AI is told never to write it, and no draft
    that writes it passes the checks. Answers your style as it is now."""
    if not book.use(change.key, change.used):
        raise HTTPException(404, "your style hasn't learned that" if not change.used else "that isn't removed")
    return your_style(book)


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
    added = [shown(m) for m in book.add(rows, "added")]
    book.learn_later()  # our AI reads them too, in the background (flip.style_ai)
    return added


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
