"""End-of-run digest to Telegram.

Preferred: the app calls the Telegram Bot API directly (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).
Optional: post the payload to an n8n webhook instead (N8N_WEBHOOK_URL), using
n8n/scholarforge_telegram_digest.json. Payload shape is the contract in the team plan."""
import datetime as dt

import requests

from core.llm import secret


def top_picks(items: list[dict], n: int = 3) -> list[dict]:
    good = [i for i in items if i["eligible"]["ok"] and not i["urgency"]["expired"]
            and i["legitimacy"]["label"] != "Likely scam"]
    return good[:n]


def build_payload(run_id: str, profile: dict, items: list[dict]) -> dict:
    return {
        "run_id": run_id,
        "profile_name": profile.get("name", "Student"),
        "top": [{"title": i["title"], "score": i["total"], "deadline": i.get("deadline"),
                 "url": i.get("source_url")} for i in top_picks(items)],
        "flagged_scams": sum(i["legitimacy"]["label"] == "Likely scam" for i in items),
    }


def _due(d: str | None) -> str:
    if not d:
        return "no deadline"
    try:
        day = dt.date.fromisoformat(d)
        return f"{day.day} {day.strftime('%b')}"
    except ValueError:
        return d


def format_message(p: dict) -> str:
    lines = [f"🎓 ScholarForge digest for {p.get('profile_name') or 'you'}", ""]
    if p.get("top"):
        lines.append("Top picks:")
        for n, t in enumerate(p["top"], 1):
            lines.append(f"{n}. {t['title']} — score {t.get('score', '?')} — due {_due(t.get('deadline'))}")
            if t.get("url"):
                lines.append(f"   {t['url']}")
    else:
        lines.append("Nothing new you can act on right now.")
    scams = p.get("flagged_scams") or 0
    if scams:
        lines += ["", f"⚠️ {scams} likely scam{'s' if scams > 1 else ''} blocked."]
    lines += ["", f"Run {p.get('run_id', '')}"]
    return "\n".join(lines)[:4000]


def configured() -> bool:
    return bool(secret("TELEGRAM_BOT_TOKEN") and secret("TELEGRAM_CHAT_ID")) or bool(secret("N8N_WEBHOOK_URL"))


def send(run_id: str, profile: dict, items: list[dict]) -> tuple[bool, str]:
    payload = build_payload(run_id, profile, items)
    token, chat_id = secret("TELEGRAM_BOT_TOKEN"), secret("TELEGRAM_CHAT_ID")
    if token and chat_id:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=10,
                              json={"chat_id": str(chat_id), "text": format_message(payload),
                                    "disable_web_page_preview": True})
        except requests.RequestException as e:  # never echo the URL: it contains the token
            return False, f"Telegram unreachable ({e.__class__.__name__})"
        if r.status_code == 200:
            return True, "Sent to Telegram"
        try:
            reason = r.json().get("description", "")
        except ValueError:
            reason = ""
        return False, f"Telegram refused (HTTP {r.status_code}) {reason}".strip()
    url = secret("N8N_WEBHOOK_URL")
    if url:
        try:
            r = requests.post(url, json=payload, timeout=10)
        except requests.RequestException as e:
            return False, f"n8n webhook unreachable ({e.__class__.__name__})"
        return r.status_code < 300, f"n8n answered HTTP {r.status_code}"
    return False, "No Telegram settings in secrets"
