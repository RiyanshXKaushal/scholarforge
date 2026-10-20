"""Profile Agent: the student's living profile, and the Scout Planner that turns it into searches."""
import json
import re

from core import prompts
from core.llm import LLMError, gemini_json, llm_available

DEMO_PROFILE = {
    "name": "Demo Student",
    "university": "LNMIIT Jaipur",
    "year": 1,
    "branch": "B.Tech Artificial Intelligence",
    "cgpa_min": 8.0,
    "cgpa_max": 8.5,
    "skills": ["Python", "n8n", "Prompt engineering"],
    "interests": ["AI agents", "Automation", "Research"],
    "goals": "Land a first internship and win hackathons",
    "location": "Remote or Jaipur",
}

KNOWN_LANGUAGES = ["Python", "JavaScript", "TypeScript", "Java", "C++", "C", "Go", "Rust",
                   "Kotlin", "Swift", "R", "Dart", "PHP", "Ruby"]
GENERIC_WORDS = {"research", "and", "the", "of", "for", "with", "in"}


def profile_text(p: dict) -> str:
    return json.dumps(p, ensure_ascii=False, indent=2)


def fallback_plan(p: dict) -> dict:
    """Rule-based plan used when Gemini is unavailable, so the agent still runs."""
    skills = [s.lower() for s in p.get("skills", [])]
    langs = [l for l in KNOWN_LANGUAGES if l.lower() in skills][:2] or ["Python"]
    words = []
    for interest in p.get("interests", []):
        for w in re.findall(r"[A-Za-z]+", interest):
            if w.lower() not in GENERIC_WORDS and w.lower() not in [x.lower() for x in words]:
                words.append(w)
    arxiv_words = words[:2] or ["machine", "learning"]
    devpost = list(dict.fromkeys([w.lower() for w in words] + ["ai"]))[:5]
    return {"github_languages": langs, "arxiv_words": arxiv_words, "devpost_keywords": devpost,
            "reasoning": "Rule-based plan from your skills and interests.", "planner": "rules"}


def plan_searches(p: dict) -> tuple[dict, str]:
    """Returns (plan, note). Uses Gemini when available, otherwise falls back to rules."""
    if not llm_available():
        return fallback_plan(p), "Gemini not configured, so I used the rule-based plan."
    try:
        plan = gemini_json(prompts.SCOUT_PLANNER.substitute(profile=profile_text(p)))
        langs = [l for l in plan.get("github_languages", []) if isinstance(l, str)][:2]
        words = [w for w in plan.get("arxiv_words", []) if isinstance(w, str)][:3]
        kws = [k.lower() for k in plan.get("devpost_keywords", []) if isinstance(k, str)][:5]
        if not (langs and words and kws):
            raise LLMError("plan was missing fields")
        return ({"github_languages": langs, "arxiv_words": words, "devpost_keywords": kws,
                 "reasoning": str(plan.get("reasoning", ""))[:300], "planner": "gemini"},
                "Gemini planned the searches from your profile.")
    except LLMError as e:
        return fallback_plan(p), f"Gemini planning failed ({e}); used the rule-based plan instead."
