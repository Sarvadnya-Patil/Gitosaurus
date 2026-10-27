"""Tiny Ollama client (stdlib only).

Configuration is read from the environment once, at import time:

    GITOSAURUS_OLLAMA_URL   address of the Ollama server   (default http://localhost:11434)
    GITOSAURUS_MODEL        model tag to use               (default gemma4:e4b; see `ollama list`)
    GITOSAURUS_KEEP_ALIVE   how long Ollama keeps the model loaded, e.g. "5m", "30m", "-1" (default 30m)
"""
import json
import os
import time
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get("GITOSAURUS_OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
DEFAULT_MODEL = os.environ.get("GITOSAURUS_MODEL", "gemma4:e4b").strip()

NUM_CTX = 8192        # warm-up and real requests must use the same value, or Ollama reloads the model
# Ollama's own default is 5m. A longer window avoids a cold start, which on a laptop with a sleeping GPU can crash
# the first load; the cost is that the model's memory stays reserved for that long.
KEEP_ALIVE = os.environ.get("GITOSAURUS_KEEP_ALIVE", "30m").strip()
RETRIES = 2           # extra attempts after a 5xx (the failed load itself wakes the GPU, so a retry works)
RETRY_WAIT_S = 4


class LLMError(RuntimeError):
    pass


def _generate(payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate", json.dumps(payload).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def ask(prompt: str, model: str = DEFAULT_MODEL, system: str = "", num_ctx: int = NUM_CTX,
        think: bool = False) -> str:
    payload = {
        "model": model, "system": system, "prompt": prompt, "stream": False, "think": think,
        "keep_alive": KEEP_ALIVE, "options": {"num_ctx": num_ctx, "temperature": 0.2},
    }
    for attempt in range(RETRIES + 1):
        try:
            return _generate(payload, timeout=300)["response"].strip()
        except urllib.error.HTTPError as e:  # Ollama is up but the request failed (e.g. the model crashed on load)
            if e.code >= 500 and attempt < RETRIES:
                time.sleep(RETRY_WAIT_S)
                continue
            try:
                detail = json.load(e).get("error", "")
            except Exception:
                detail = ""
            hint = " Ollama may be low on memory or its GPU runner crashed. Try again, or restart Ollama." \
                if e.code >= 500 else ""
            raise LLMError(f"Ollama couldn't run the model (HTTP {e.code}). {detail[:200]}{hint}".strip()) from e
        except urllib.error.URLError as e:
            raise LLMError(f"Cannot reach Ollama at {OLLAMA_URL}. Is it running? ({e.reason})") from e
        except TimeoutError as e:
            raise LLMError("Ollama took too long to answer (the model may still be loading). Try again.") from e
    raise LLMError("Ollama didn't respond.")  # unreachable; keeps the function total


def warm_up(model: str = DEFAULT_MODEL) -> None:
    """Load the model into memory ahead of the first question. Best effort: never raises.

    An empty prompt loads the model without generating anything. Run it in a background thread.
    """
    payload = {"model": model, "prompt": "", "stream": False, "keep_alive": KEEP_ALIVE,
               "options": {"num_ctx": NUM_CTX}}
    for attempt in range(RETRIES + 1):
        try:
            _generate(payload, timeout=300)
            return
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return
            time.sleep(RETRY_WAIT_S)
        except Exception:
            return
