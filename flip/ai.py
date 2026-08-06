"""The two AI models behind one small plug: ask(system, user, photos, schema)
returns a Reply, whichever model answers.

The local model (Gemma 3 4B through Ollama) runs on this Mac: free, and nothing
leaves the machine. The API model (Claude Haiku) is paid and only gets items
whose local answer failed the checks. "Couldn't be reached" and "answered
wrongly" are kept apart, because only a wrong answer may go on to the API.
"""

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

import anthropic


@dataclass
class Reply:
    model: str
    answer: dict | None = None  # the parsed answer, or None if the call failed
    error: str = ""             # why it failed
    reachable: bool = True      # False when the model couldn't be reached at all
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float = 0.0


def parse_answer(text):
    """The answer as a dict, and an error if it isn't one."""
    try:
        answer = json.loads(text)
    except (TypeError, ValueError):
        return None, "the answer isn't valid JSON"
    if not isinstance(answer, dict):
        return None, "the answer isn't a JSON object"
    return answer, ""


class LocalModel:
    """Gemma 3 4B through Ollama on this Mac."""

    def __init__(self, name="gemma3:4b", url="http://127.0.0.1:11434", timeout=300):
        self.name, self.url, self.timeout = name, url, timeout

    def ask(self, system, user, photos, schema):
        body = {
            "model": self.name,
            "stream": False,
            "format": schema,  # held to the shape while it writes
            "keep_alive": "30m",  # stay loaded between items
            # Ollama's defaults are a random answer (temperature 1) and a short
            # memory (4,096 tokens). Same input, same answer; room for photos.
            "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 1000},
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
            return Reply(self.name, error=f"the local model refused ({e.code}): {e.read().decode()[:200]}",
                         reachable=False, seconds=time.monotonic() - started)
        except urllib.error.URLError as e:
            return Reply(self.name, error=f"the local model isn't running ({e.reason})", reachable=False,
                         seconds=time.monotonic() - started)
        except TimeoutError:
            return Reply(self.name, error="the local model took too long", seconds=time.monotonic() - started)
        reply = Reply(self.name, tokens_in=data.get("prompt_eval_count", 0), tokens_out=data.get("eval_count", 0),
                      seconds=time.monotonic() - started)
        if data.get("done_reason") == "length":
            reply.error = "the answer was cut off"
            return reply
        reply.answer, reply.error = parse_answer(data.get("message", {}).get("content", ""))
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
