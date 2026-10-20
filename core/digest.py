"""Posts the end-of-run digest to the n8n webhook, which sends it to Telegram.
Payload shape is the contract in the team plan, section 'Digest webhook'."""
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


def send(run_id: str, profile: dict, items: list[dict]) -> tuple[bool, str]:
    url = secret("N8N_WEBHOOK_URL")
    if not url:
        return False, "No N8N_WEBHOOK_URL in secrets"
    try:
        r = requests.post(url, json=build_payload(run_id, profile, items), timeout=10)
    except requests.RequestException as e:
        return False, f"Webhook unreachable ({e.__class__.__name__})"
    return (r.status_code < 300), f"n8n answered HTTP {r.status_code}"
