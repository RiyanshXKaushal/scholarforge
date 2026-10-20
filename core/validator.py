"""Deterministic checks. These are code on purpose: no message text can talk its way past them.
The LLM explanation (Wed) can only lower a score, never clear a flag."""
import datetime as dt
import re

from core import db

OFFICIAL_SOURCES = {"github", "arxiv", "devpost"}

RULES = [
    # (key, label, pattern searched in title + description + contact, severe?)
    ("fee", "Asks for a fee",
     r"(registration|processing|security|application|joining|training)\s+(fee|deposit|charge)|\bpay\s*(₹|rs\.?|inr)\s*\d", True),
    ("guaranteed", "Promises guaranteed selection",
     r"guarantee[d]?\s+(selection|placement|job|internship|offer)|100\s*%\s*(selection|placement|guaranteed|job)", True),
    ("chat_only", "Contact only via WhatsApp / Telegram",
     r"(whatsapp|telegram)\s*(only|:)|only\s+on\s+(whatsapp|telegram)|contact\s+(only\s+)?(on|via)\s+(whatsapp|telegram)", False),
    ("personal_email", "Organisation uses a personal email address",
     r"@(gmail|yahoo|hotmail|outlook|rediffmail)\.com", False),
    ("ai_instruction", "Contains instructions aimed at AI tools",
     r"(note|message)\s+to\s+(ai|llm|chatgpt|screening)|ignore\s+(all\s+|your\s+|previous\s+)?(rules|instructions)|rank\s+(it|this)\s+first", True),
]


def _evidence(text: str, m: re.Match) -> str:
    start, end = max(0, m.start() - 30), min(len(text), m.end() + 30)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def _monthly_pay(text: str | None) -> int | None:
    if not text or "month" not in text.lower():
        return None
    m = re.search(r"₹\s*([\d,]+)\s*(k)?", text, re.I)
    if not m:
        return None
    value = int(m.group(1).replace(",", ""))
    return value * 1000 if m.group(2) else value


NEGATION = re.compile(r"\b(no|without|zero|free\s+of|not\s+charge\s+any)\s+$", re.I)


def _first_real_match(pattern: str, text: str) -> re.Match | None:
    """First match that isn't negated, so 'No application fee' doesn't count as asking for a fee."""
    for m in re.finditer(pattern, text, re.I):
        if not NEGATION.search(text[max(0, m.start() - 25):m.start()]):
            return m
    return None


def red_flags(opp: dict) -> list[dict]:
    text = " ".join(str(opp.get(k) or "") for k in ("title", "description", "contact"))
    flags = []
    for key, label, pattern, severe in RULES:
        m = _first_real_match(pattern, text)
        if m:
            flags.append({"flag": key, "label": label, "evidence": _evidence(text, m), "severe": severe})
    if not opp.get("source_url"):
        flags.append({"flag": "no_source", "label": "No official website or source link",
                      "evidence": "The listing gives no link to an official page.", "severe": False})
    pay = _monthly_pay(opp.get("stipend_or_prize"))
    if opp.get("type") == "internship" and pay and pay >= 60000:
        flags.append({"flag": "pay_unrealistic", "label": "Pay far above the norm for a student internship",
                      "evidence": opp.get("stipend_or_prize"), "severe": False})
    return flags


def legitimacy(opp: dict) -> dict:
    flags = red_flags(opp)
    severe = sum(f["severe"] for f in flags)
    score = max(0, 100 - 35 * severe - 15 * (len(flags) - severe))
    if severe or len(flags) >= 2:
        label = "Likely scam"
    elif flags:
        label = "Caution"
    elif opp.get("source") in OFFICIAL_SOURCES:
        label = "Verified source"
    else:
        label = "No red flags"
    return {"score": score, "label": label, "red_flags": flags}


def eligibility(opp: dict, profile: dict) -> dict:
    rules = opp.get("eligibility") or {}
    years = rules.get("years") or []
    if years and profile.get("year") not in years:
        names = ", ".join(f"year {y}" for y in years)
        return {"ok": False, "reason": f"Open to {names} only; you're in year {profile.get('year')}"}
    min_cgpa = rules.get("min_cgpa")
    if min_cgpa and (profile.get("cgpa_max") or 0) < min_cgpa:
        return {"ok": False, "reason": f"Needs CGPA {min_cgpa}+; your range tops out at {profile.get('cgpa_max')}"}
    branches = [b.lower() for b in rules.get("branches") or ["any"]]
    if "any" not in branches:
        mine = (profile.get("branch") or "").lower()
        aliases = {"ai": "artificial intelligence", "cse": "computer science", "ece": "electronics"}
        if not any(b in mine or aliases.get(b, "\0") in mine for b in branches):
            return {"ok": False, "reason": f"Open to {', '.join(rules['branches'])} only"}
    return {"ok": True, "reason": "You meet the stated year, CGPA and branch requirements"}


def urgency(opp: dict, today: dt.date | None = None) -> dict:
    today = today or db.now().date()
    if not opp.get("deadline"):
        return {"days_left": None, "score": 40, "expired": False, "label": "No deadline listed"}
    try:
        deadline = dt.date.fromisoformat(opp["deadline"])
    except ValueError:
        return {"days_left": None, "score": 40, "expired": False, "label": "Deadline unreadable"}
    days = (deadline - today).days
    if days < 0:
        return {"days_left": days, "score": 0, "expired": True, "label": f"Expired {-days} days ago"}
    score = 100 if days <= 3 else 85 if days <= 7 else 70 if days <= 14 else 50 if days <= 30 else 30
    label = "Due today" if days == 0 else f"{days} day{'s' if days != 1 else ''} left"
    return {"days_left": days, "score": score, "expired": False, "label": label}


def _key(opp: dict) -> str:
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    return norm(opp.get("organisation")) + "|" + norm(opp.get("title"))


def dedupe(items: list[dict]) -> tuple[list[dict], int]:
    seen, out, merged = {}, [], 0
    for it in items:
        k = _key(it)
        if k in seen:
            first = seen[k]
            first.setdefault("also_seen_at", []).append(
                {"source": it.get("source"), "url": it.get("source_url"), "id": it.get("id")})
            merged += 1
        else:
            seen[k] = it
            out.append(it)
    return out, merged


def assess(items: list[dict], profile: dict) -> list[dict]:
    for it in items:
        it["legitimacy"] = legitimacy(it)
        it["eligible"] = eligibility(it, profile)
        it["urgency"] = urgency(it)
        # Provisional score until the Ranker (fit + value) ships on Wed.
        it["total"] = round(0.6 * it["legitimacy"]["score"] + 0.4 * it["urgency"]["score"])
        it["total_is_provisional"] = True

    def sort_key(it):
        blocked = it["legitimacy"]["label"] == "Likely scam" or it["urgency"]["expired"] or not it["eligible"]["ok"]
        return (blocked, -it["total"])

    return sorted(items, key=sort_key)
