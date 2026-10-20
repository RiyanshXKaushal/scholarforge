"""Scout Agents. Each takes the plan + profile and returns (opportunities, detail).
A scout that can't reach its source raises ScoutError with a readable reason;
the orchestrator shows that as a failed step instead of hiding it. Nothing is invented."""
import datetime as dt
import html
import re
import xml.etree.ElementTree as ET

import requests

from core import db
from core.llm import secret

TIMEOUT = 15
UA = "ScholarForge/1.0 (student hackathon project)"


class ScoutError(Exception):
    pass


def make_opp(**kw) -> dict:
    base = {"id": "", "title": "", "organisation": None, "type": "internship", "source": "",
            "source_url": None, "fetched_at": db.now_iso(), "deadline": None,
            "eligibility": {"years": [], "min_cgpa": None, "branches": ["any"]},
            "stipend_or_prize": None, "location": None, "contact": None, "description": "",
            "is_sample": False}
    base.update(kw)
    return base


def _get(url, **kw):
    try:
        r = requests.get(url, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        raise ScoutError(f"could not reach {url.split('/')[2]} ({e.__class__.__name__})")
    return r


# --- Scout · Open-source --------------------------------------------------------------
def github_scout(plan: dict, profile: dict) -> tuple[list[dict], str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    token = secret("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    found = []
    for lang in plan.get("github_languages", ["Python"])[:2]:
        q = f'label:"good first issue" state:open is:issue no:assignee language:{lang}'
        r = _get("https://api.github.com/search/issues", headers=headers,
                 params={"q": q, "sort": "updated", "order": "desc", "per_page": 4})
        if r.status_code in (403, 429):
            raise ScoutError("GitHub rate limit reached. Add a GITHUB_TOKEN to secrets, or wait a minute.")
        if r.status_code != 200:
            raise ScoutError(f"GitHub returned HTTP {r.status_code}")
        for it in r.json().get("items", []):
            repo = it.get("repository_url", "").replace("https://api.github.com/repos/", "")
            body = (it.get("body") or "").strip()
            found.append(make_opp(
                id=f"gh-{it.get('id')}", title=it.get("title", "Untitled issue"), organisation=repo,
                type="open_source", source="github", source_url=it.get("html_url"),
                stipend_or_prize="Unpaid · open-source contribution", location="Remote",
                description=(f"Good first issue in {repo} ({lang}). " + re.sub(r"\s+", " ", body))[:600]))
    return found, f"{len(found)} open good-first issues in {', '.join(plan.get('github_languages', [])[:2])}"


# --- Scout · Research ---------------------------------------------------------------------
ATOM = {"a": "http://www.w3.org/2005/Atom"}


def arxiv_scout(plan: dict, profile: dict) -> tuple[list[dict], str]:
    words = [re.sub(r"[^A-Za-z0-9]", "", w) for w in plan.get("arxiv_words", [])][:3]
    words = [w for w in words if w] or ["agents"]
    query = " AND ".join(f"all:{w}" for w in words)
    r = _get("https://export.arxiv.org/api/query", headers={"User-Agent": UA},
             params={"search_query": query, "sortBy": "submittedDate", "sortOrder": "descending", "max_results": 4})
    if r.status_code != 200:
        raise ScoutError(f"arXiv returned HTTP {r.status_code}")
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        raise ScoutError("arXiv sent a response I couldn't parse")
    found = []
    for e in root.findall("a:entry", ATOM):
        title = re.sub(r"\s+", " ", e.findtext("a:title", "", ATOM)).strip()
        summary = re.sub(r"\s+", " ", e.findtext("a:summary", "", ATOM)).strip()
        link = e.findtext("a:id", "", ATOM).strip()
        authors = [a.findtext("a:name", "", ATOM) for a in e.findall("a:author", ATOM)]
        lead = authors[0] + (" et al." if len(authors) > 1 else "") if authors else "arXiv authors"
        found.append(make_opp(
            id=f"arxiv-{link.rsplit('/', 1)[-1]}", title=f"Read and reach out: {title}", organisation=lead,
            type="research", source="arxiv", source_url=link, stipend_or_prize="Unpaid · research contact",
            location="Remote", description=f"Recent paper ({e.findtext('a:published', '', ATOM)[:10]}). {summary}"[:600]))
    return found, f"{len(found)} recent papers for “{' '.join(words)}”"


# --- Scout · Hackathons ----------------------------------------------------------------------
MONTHS = "%b %d, %Y"


def parse_devpost_deadline(period: str) -> str | None:
    """'Aug 31 - Oct 23, 2026' -> '2026-10-23'; 'Oct 19 - 23, 2026' -> '2026-10-23'."""
    if not period or " - " not in period:
        return None
    start, end = [s.strip() for s in period.split(" - ", 1)]
    for candidate in (end, f"{start.split()[0]} {end}"):
        try:
            return dt.datetime.strptime(candidate, MONTHS).date().isoformat()
        except ValueError:
            continue
    return None


def devpost_scout(plan: dict, profile: dict) -> tuple[list[dict], str]:
    hackathons = []
    for page in (1, 2):
        r = _get("https://devpost.com/api/hackathons", headers={"User-Agent": UA, "Accept": "application/json"},
                 params={"status[]": "open", "page": page})
        if r.status_code != 200:
            raise ScoutError(f"Devpost returned HTTP {r.status_code}")
        try:
            hackathons += r.json().get("hackathons", [])
        except ValueError:
            raise ScoutError("Devpost sent a response I couldn't parse")
    kws = [k.lower() for k in plan.get("devpost_keywords", [])]

    def matches(h):
        text = (h.get("title", "") + " " + " ".join(t.get("name", "") for t in h.get("themes", []))).lower()
        return any(re.search(rf"\b{re.escape(k)}\b", text) for k in kws)

    picked = [h for h in hackathons if matches(h)][:5]
    found = []
    for h in picked:
        prize = html.unescape(re.sub(r"<[^>]+>", "", h.get("prize_amount", "") or "")).strip()
        themes = ", ".join(t.get("name", "") for t in h.get("themes", []))
        found.append(make_opp(
            id=f"devpost-{h.get('id')}", title=h.get("title", "Hackathon"), organisation=h.get("organization_name"),
            type="hackathon", source="devpost", source_url=h.get("url"),
            deadline=parse_devpost_deadline(h.get("submission_period_dates", "")),
            stipend_or_prize=f"{prize} in prizes" if prize else None,
            location=(h.get("displayed_location") or {}).get("location"),
            description=f"Open hackathon on Devpost. Themes: {themes}. Submission period: "
                        f"{h.get('submission_period_dates', 'not listed')}. {h.get('registrations_count', 0)} registered."))
    return found, f"{len(found)} of {len(hackathons)} open hackathons match {', '.join(kws)}"


# --- Scout · Sample library -------------------------------------------------------------------
def sample_scout(plan: dict, profile: dict) -> tuple[list[dict], str]:
    items = db.load_samples()
    return items, f"{len(items)} tagged demo opportunities (marked Sample)"


# --- Scout · Inbox (page arrives Thu) ---------------------------------------------------------
def inbox_scout(plan: dict, profile: dict) -> tuple[list[dict], str]:
    pending = db.unprocessed_inbox()
    if not pending:
        return [], "No forwarded items waiting"
    return [], f"{len(pending)} forwarded items waiting (extraction ships with the Inbox page)"


SCOUTS = [
    ("scout_github", "Scout · Open-source — GitHub “good first issue”", github_scout),
    ("scout_arxiv", "Scout · Research — arXiv", arxiv_scout),
    ("scout_devpost", "Scout · Hackathons — Devpost", devpost_scout),
    ("scout_samples", "Scout · Sample library", sample_scout),
    ("scout_inbox", "Scout · Inbox — forwarded messages", inbox_scout),
]
