"""Gemini over plain REST, in JSON mode. Keys live in Streamlit secrets, never in code."""
import base64
import json

import requests
import streamlit as st

DEFAULT_MODEL = "gemini-flash-latest"


class LLMError(Exception):
    """Raised with a human-readable reason whenever the LLM can't give a usable answer."""


def secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:  # no secrets file at all
        return default


def llm_available() -> bool:
    return bool(secret("GEMINI_API_KEY"))


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


def gemini_json(prompt: str, image_bytes: bytes | None = None, image_mime: str = "image/png",
                temperature: float = 0.2, timeout: int = 40) -> dict:
    key = secret("GEMINI_API_KEY")
    if not key:
        raise LLMError("No GEMINI_API_KEY in Streamlit secrets")
    model = secret("GEMINI_MODEL", DEFAULT_MODEL)

    parts = [{"text": prompt}]
    if image_bytes:
        parts.append({"inline_data": {"mime_type": image_mime,
                                      "data": base64.b64encode(image_bytes).decode()}})
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    try:
        r = requests.post(url, json=body, timeout=timeout,
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    except requests.RequestException as e:
        raise LLMError(f"Gemini request failed: {e.__class__.__name__}")
    if r.status_code == 429:
        raise LLMError("Gemini rate limit hit (429). Wait a minute and run again.")
    if r.status_code == 404:
        raise LLMError(f"Model '{model}' not found. Set GEMINI_MODEL in secrets to a model listed in Google AI Studio.")
    if r.status_code != 200:
        raise LLMError(f"Gemini returned HTTP {r.status_code}: {r.text[:160]}")
    try:
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(_strip_fences(text))
    except (KeyError, IndexError, ValueError) as e:
        raise LLMError(f"Could not read Gemini's JSON answer ({e.__class__.__name__})")
