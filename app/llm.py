# app/llm.py
"""
Provider-agnostic LLM access.

Model ids follow one convention:
  * ``gemini/<model>``  -> Google Gemini API directly (needs GOOGLE_API_KEY)
  * anything else       -> OpenRouter (needs OPENROUTER_API_KEY), e.g. ``anthropic/claude-sonnet-5.5``

If a Gemini model is requested but only an OpenRouter key is configured, the call is
transparently routed through OpenRouter as ``google/<model>``.
"""
import json
import logging
import os
import re
import threading
import time

import requests

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_MODEL = f"gemini/{DEFAULT_GEMINI_MODEL}"

# Curated list shown in the UI. Any other OpenRouter id can still be typed in as a custom model.
MODEL_CATALOG = [
    {"id": "gemini/gemini-3-flash-preview", "label": "Gemini 3 Flash (preview)", "provider": "google"},
    {"id": "gemini/gemini-2.5-pro", "label": "Gemini 2.5 Pro", "provider": "google"},
    {"id": "gemini/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "provider": "google"},
    {"id": "anthropic/claude-sonnet-5.5", "label": "Claude Sonnet 5.5", "provider": "openrouter"},
    {"id": "anthropic/claude-opus-5.5", "label": "Claude Opus 5.5", "provider": "openrouter"},
    {"id": "anthropic/claude-haiku-5.5", "label": "Claude Haiku 5.5", "provider": "openrouter"},
    {"id": "openai/gpt-5.5", "label": "GPT-5.5", "provider": "openrouter"},
    {"id": "google/gemini-3.1-pro-preview", "label": "Gemini 3.1 Pro (via OpenRouter)", "provider": "openrouter"},
    {"id": "x-ai/grok-4.7", "label": "Grok 4.7", "provider": "openrouter"},
    {"id": "moonshotai/kimi-k3", "label": "Kimi K3", "provider": "openrouter"},
    {"id": "qwen/qwen3.7-plus", "label": "Qwen 3.7 Plus", "provider": "openrouter"},
    {"id": "deepseek/deepseek-v4-flash", "label": "DeepSeek V4 Flash", "provider": "openrouter"},
    {"id": "nvidia/nemotron-3-super-120b-a12b:free", "label": "Nemotron 3 Super (free)", "provider": "openrouter"},
    {"id": "google/gemma-4-31b-it:free", "label": "Gemma 4 31B (free)", "provider": "openrouter"},
]

# Ids used by older versions of the UI, mapped to their current equivalent.
LEGACY_MODEL_ALIASES = {
    "google/gemini-pro": DEFAULT_MODEL,
}

MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
REQUEST_TIMEOUT = (10, 300)  # (connect, read) seconds


class LLMError(Exception):
    """Raised when a model call fails; the message is safe to show to the user."""


class LLMConfigError(LLMError):
    """Raised when the requested provider has no API key configured."""


def _google_key() -> str | None:
    return os.environ.get("GOOGLE_API_KEY") or None


def _openrouter_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY") or None


def provider_status() -> dict:
    return {"google": bool(_google_key()), "openrouter": bool(_openrouter_key())}


def available_models() -> list[dict]:
    """The model catalog, annotated with whether each model is usable with the configured keys."""
    status = provider_status()
    models = []
    for entry in MODEL_CATALOG:
        usable = status[entry["provider"]] or (entry["provider"] == "google" and status["openrouter"])
        models.append({**entry, "available": usable})
    return models


def resolve_model(model: str | None) -> tuple[str, str]:
    """Returns (provider, provider_model_name) for a UI model id."""
    model = (model or "").strip() or DEFAULT_MODEL
    model = LEGACY_MODEL_ALIASES.get(model, model)

    if model.startswith("gemini/"):
        name = model.split("/", 1)[1] or DEFAULT_GEMINI_MODEL
        if _google_key():
            return "google", name
        if _openrouter_key():
            return "openrouter", f"google/{name}"
        raise LLMConfigError("No GOOGLE_API_KEY (or OPENROUTER_API_KEY) is configured for Gemini models. Add one to your .env file.")

    if not _openrouter_key():
        raise LLMConfigError(f"Model '{model}' runs through OpenRouter, but OPENROUTER_API_KEY is not configured. Add it to your .env file.")
    return "openrouter", model


def call_llm(prompt: str, model: str | None = None, *, system: str | None = None,
             json_mode: bool = False, temperature: float | None = None) -> str:
    """Sends a single-turn prompt and returns the text reply. Raises LLMError on failure."""
    provider, name = resolve_model(model)
    logger.info("LLM call: provider=%s model=%s json_mode=%s prompt_chars=%d", provider, name, json_mode, len(prompt))
    started = time.monotonic()
    if provider == "google":
        text = _with_retries(lambda: _call_gemini(name, prompt, system, json_mode, temperature))
    else:
        text = _with_retries(lambda: _call_openrouter(name, prompt, system, json_mode, temperature))
    logger.info("LLM reply from %s in %.1fs (%d chars)", name, time.monotonic() - started, len(text))
    return text


class _RetryableError(LLMError):
    pass


def _with_retries(fn):
    delay = 2.0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return fn()
        except _RetryableError as e:
            if attempt == MAX_ATTEMPTS:
                raise LLMError(str(e)) from e
            logger.warning("Retryable LLM error (attempt %d/%d): %s. Retrying in %.0fs.", attempt, MAX_ATTEMPTS, e, delay)
            time.sleep(delay)
            delay *= 2


# --- Google Gemini ---------------------------------------------------------

_gemini_clients: dict[str, object] = {}
_gemini_lock = threading.Lock()


def _gemini_client(api_key: str):
    from google import genai
    with _gemini_lock:
        if api_key not in _gemini_clients:
            _gemini_clients[api_key] = genai.Client(api_key=api_key)
        return _gemini_clients[api_key]


def _call_gemini(model_name, prompt, system, json_mode, temperature) -> str:
    from google.genai import errors, types

    config_kwargs = {}
    if system:
        config_kwargs["system_instruction"] = system
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    if temperature is not None:
        config_kwargs["temperature"] = temperature

    try:
        response = _gemini_client(_google_key()).models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
        )
    except errors.APIError as e:
        message = f"Gemini API error ({e.code}): {e.message or e}"
        if e.code in RETRYABLE_STATUS:
            raise _RetryableError(message) from e
        raise LLMError(message) from e
    except Exception as e:  # network errors etc.
        raise _RetryableError(f"Gemini request failed: {e}") from e

    text = getattr(response, "text", None)
    if not text:
        feedback = getattr(response, "prompt_feedback", None)
        raise LLMError(f"Gemini returned an empty response{f' ({feedback})' if feedback else ''}.")
    return text


# --- OpenRouter ------------------------------------------------------------

def _call_openrouter(model_name, prompt, system, json_mode, temperature) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body = {"model": model_name, "messages": messages}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if temperature is not None:
        body["temperature"] = temperature

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {_openrouter_key()}",
                "Content-Type": "application/json",
                "X-Title": "AI CV Tailor",
            },
            data=json.dumps(body),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        raise _RetryableError(f"OpenRouter request failed: {e}") from e

    try:
        payload = response.json()
    except ValueError:
        payload = {}

    error = payload.get("error") if isinstance(payload, dict) else None
    if response.status_code >= 400 or error:
        detail = error.get("message") if isinstance(error, dict) else (error or response.text[:300])
        status = response.status_code if response.status_code >= 400 else (error.get("code") if isinstance(error, dict) else None)
        message = f"OpenRouter error ({status}) for '{model_name}': {detail}"
        if status in RETRYABLE_STATUS:
            raise _RetryableError(message)
        raise LLMError(message)

    try:
        content = payload["choices"][0]["message"].get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise LLMError(f"OpenRouter returned an unexpected response for '{model_name}'.")
    if not content:
        raise LLMError(f"'{model_name}' returned an empty response. Try again or pick another model.")
    return content


# --- Output helpers --------------------------------------------------------

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str):
    """
    Pulls the first JSON object out of a model reply, tolerating reasoning blocks,
    markdown fences and surrounding prose. Raises ValueError if nothing parses.
    """
    if not text:
        raise ValueError("Empty model output")
    cleaned = _THINK_BLOCK.sub("", text).strip()

    candidates = [cleaned]
    candidates.extend(m.group(1).strip() for m in _CODE_FENCE.finditer(cleaned))

    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        for match in re.finditer(r"\{", candidate):
            try:
                obj, _ = decoder.raw_decode(candidate, match.start())
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    raise ValueError("No valid JSON object found in model output")


def strip_reasoning(text: str) -> str:
    """Removes <think> blocks some reasoning models emit inline."""
    return _THINK_BLOCK.sub("", text or "").strip()
