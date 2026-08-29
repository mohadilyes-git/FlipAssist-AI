"""The two AI models behind one small plug: ask(system, user, photos, schema)
returns a Reply, whichever model answers.

The local model (Gemma 3 4B through Ollama) runs on this Mac: free, and nothing
leaves the machine. The API model (Claude Haiku) is paid and only gets items
whose local answer failed the checks. "Couldn't be reached" and "answered
wrongly" are kept apart, because only a wrong answer may go on to the API.
"""

import http.client
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import anthropic

# Gemma sometimes ends its JSON with a curly quote (”}) instead of a straight
# one. JSON doesn't take ” as the end of the text, so it would write filler
# ("✉️ ✉️ ✉️") until the token limit, half a minute later. It stops there
# instead, and the text is closed for it (ollama_text)
CURLY_ENDS = ["”}", "”\n}", "” }"]


@dataclass
class Reply:
    model: str
    answer: dict | None = None  # the parsed answer, or None if the call failed
    error: str = ""             # why it failed
    reachable: bool = True      # False when the model couldn't be reached at all
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0


HALF_CHARACTER = re.compile("[\ud800-\udfff]")  # a whole pair is one character by now: only halves are left


def ollama_text(data):
    """The answer's text from Ollama's reply. If it stopped at a curly end, the
    text is closed the way it should have been: "...cash.”} -> ...cash."}"""
    text = whole_text(data["message"]["content"])
    if data.get("done_reason") == "stop" and not text.rstrip().endswith("}"):
        text += '"}'
    return text


def whole_text(value):
    """Text, or JSON made of it, with any half character made "�", the sign
    for one that can't be shown. JSON can spell half a character (\\ud800):
    Python takes it, but nothing can write it out again, the audit log included."""
    if isinstance(value, str):
        return HALF_CHARACTER.sub("\ufffd", value)
    if isinstance(value, list):
        return [whole_text(v) for v in value]
    if isinstance(value, dict):
        return {whole_text(k): whole_text(v) for k, v in value.items()}
    return value


def ollama_shaped(data):
    """Whether a reply is shaped like Ollama's: a message with text in it."""
    return isinstance(data, dict) and isinstance(data.get("message"), dict) \
        and isinstance(data["message"].get("content"), str)


def count(tokens):
    """A token count as Ollama gives it, or 0 for one that can't be: not a whole number, below 0, or absurd."""
    return tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and 0 <= tokens < 10**9 else 0


def said(error):
    """What an HTTP error's page says, if it can be read: it may be in any encoding, or hang up halfway."""
    try:
        return error.read(2000).decode("utf-8", "replace")[:200]
    except (OSError, http.client.HTTPException, ValueError):
        return "no reason given"


def parse_answer(text):
    """The answer as a dict, and an error if it isn't one."""
    try:
        answer = whole_text(json.loads(text))
    except (TypeError, ValueError, RecursionError):
        return None, "the answer isn't valid JSON"
    if not isinstance(answer, dict):
        return None, "the answer isn't a JSON object"
    return answer, ""


class LocalModel:
    """Gemma 3 4B through Ollama on this Mac."""

    def __init__(self, name="gemma3:4b", url="http://127.0.0.1:11434", timeout=300, max_tokens=1000):
        self.name, self.url, self.timeout, self.max_tokens = name, url, timeout, max_tokens

    def ask(self, system, user, photos, schema):
        body = {
            "model": self.name,
            "stream": False,
            "format": schema,  # held to the shape while it writes
            "keep_alive": "30m",  # stay loaded between items
            # Ollama's defaults are a random answer (temperature 1) and a short
            # memory (4,096 tokens). Same input, same answer; room for photos.
            "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": self.max_tokens,
                        "stop": CURLY_ENDS},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user, "images": list(photos)}],
        }
        request = urllib.request.Request(f"{self.url}/api/chat", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.load(response)
        except urllib.error.HTTPError as e:  # e.g. the model isn't downloaded
            return Reply(self.name, error=f"the local model refused ({e.code}): {said(e)}",
                         reachable=False, seconds=time.monotonic() - started)
        except urllib.error.URLError as e:
            return Reply(self.name, error=f"the local model isn't running ({e.reason})", reachable=False,
                         seconds=time.monotonic() - started)
        except TimeoutError:  # minutes with no answer: as good as not running, so it isn't sent to the API instead
            return Reply(self.name, error="the local model took too long", reachable=False,
                         seconds=time.monotonic() - started)
        except (ConnectionError, http.client.HTTPException) as e:  # it quit, restarted or crashed mid-answer
            return Reply(self.name, error=f"the local model stopped answering ({type(e).__name__})", reachable=False,
                         seconds=time.monotonic() - started)
        except (OSError, ValueError, RecursionError):  # not Ollama's JSON: something else is on its port
            return Reply(self.name, error="the local model's answer couldn't be read", reachable=False,
                         seconds=time.monotonic() - started)
        if not ollama_shaped(data):
            return Reply(self.name, error="the local model's answer couldn't be read", reachable=False,
                         seconds=time.monotonic() - started)
        reply = Reply(self.name, tokens_in=count(data.get("prompt_eval_count")), tokens_out=count(data.get("eval_count")),
                      seconds=time.monotonic() - started)
        if data.get("done_reason") == "length":
            reply.error = "the answer was cut off"
            return reply
        reply.answer, reply.error = parse_answer(ollama_text(data))
        return reply


class ApiModel:
    """Claude Haiku through the Anthropic API, for answers the local model got wrong."""

    def __init__(self, name="claude-haiku-5-5", client=None):
        self.name, self.client = name, client  # the client is made on first use

    def ask(self, system, user, photos, schema):
        started = time.monotonic()
        try:
            self.client = self.client or anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
            response = self.client.messages.create(
                model=self.name,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": [
                    *({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": photo}}
                      for photo in photos),
                    {"type": "text", "text": user},
                ]}],
                # low effort: it thinks less, and thinking is billed. The format
                # holds it to the shape. No temperature: this API no longer takes one
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.APIConnectionError:
            return Reply(self.name, error="couldn't reach the API", reachable=False,
                         seconds=time.monotonic() - started)
        except anthropic.APIStatusError as e:
            return Reply(self.name, error=f"the API said {e.status_code}: {e.message}",
                         seconds=time.monotonic() - started)
        except anthropic.AnthropicError as e:  # e.g. no API key set
            return Reply(self.name, error=f"the API can't be used: {e}", reachable=False,
                         seconds=time.monotonic() - started)
        reply = Reply(self.name, tokens_in=response.usage.input_tokens, tokens_out=response.usage.output_tokens,
                      seconds=time.monotonic() - started)
        if response.stop_reason in ("refusal", "max_tokens"):
            reply.error = f"the API stopped early ({response.stop_reason})"
            return reply
        reply.answer, reply.error = parse_answer(next((b.text for b in response.content if b.type == "text"), ""))
        return reply
