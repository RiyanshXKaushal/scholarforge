"""The Streamlit pages."""
import streamlit as st

from core import db
from core.llm import llm_available, secret
from core.orchestrator import run_agent
from core.profile import DEMO_PROFILE

LEGIT_STYLE = {"Likely scam": "red", "Caution": "orange", "Verified source": "green", "No red flags": "blue"}
TYPE_NAMES = {"internship": "Internship", "scholarship": "Scholarship", "hackathon": "Hackathon",
              "open_source": "Open source", "research": "Research"}


class StreamlitUI:
    """Bridges orchestrator events to live st.status boxes."""

    def __init__(self, container):
        self.c, self.boxes, self.labels = container, {}, {}

    def start(self, step, label):
        self.labels[step] = label
        self.boxes[step] = self.c.status(f"{label}…", state="running", expanded=False)

    def finish(self, step, ok, detail, items=0):
        box = self.boxes[step]
        box.write(detail)
        suffix = f" — {items} items" if items else ""
        box.update(label=self.labels[step] + (suffix if ok else " — failed"),
                   state="complete" if ok else "error", expanded=not ok)


def _sidebar_status():
    with st.sidebar:
        st.caption("Connections")
        st.write(("🟢" if llm_available() else "⚪") + " Gemini " + ("connected" if llm_available() else "not configured"))
        st.write(("🟢" if secret("N8N_WEBHOOK_URL") else "⚪") + " Telegram digest " +
                 ("on" if secret("N8N_WEBHOOK_URL") else "off"))
        st.write(("🟢" if secret("GITHUB_TOKEN") else "⚪") + " GitHub token " +
                 ("set" if secret("GITHUB_TOKEN") else "not set (lower rate limit)"))


def run_page():
    _sidebar_status()
    p = db.get_profile()
    st.title("Run Agent")
    st.caption(f"Searching for **{p.get('name')}** · year {p.get('year')} · {p.get('branch')} · "
               f"interests: {', '.join(p.get('interests', []))}")
    clicked = st.button("Run Agent", type="primary", icon=":material/play_arrow:")
    timeline = st.container()
    if clicked:
        result = run_agent(StreamlitUI(timeline))
        items = result["items"]
        good = sum(i["eligible"]["ok"] and not i["urgency"]["expired"] and i["legitimacy"]["label"] != "Likely scam"
                   for i in items)
        msg = f"Found {len(items)} opportunities · {good} you can act on now"
        if result["failed_scouts"]:
            st.warning(msg + f" · {result['failed_scouts']} scout(s) failed — see the red steps above")
        else:
            st.success(msg)
        st.page_link(st.session_state["_results_page"], label="See ranked results", icon=":material/list:")
        return
    last = db.latest_run()
    if not last:
        st.info("No runs yet. Click Run Agent to start.")
        return
    timeline.caption(f"Last run {last['id']} · {last['status']} · {last['started_at'][:16].replace('T', ' ')}")
    for s in db.run_steps(last["id"]):
        state = {"done": "complete", "failed": "error"}.get(s["status"], "running")
        suffix = f" — {s['items']} items" if s["items"] else ""
        with timeline.status(s["label"] + (suffix if state == "complete" else " — failed" if state == "error" else ""),
                             state=state, expanded=False):
            st.write(s["detail"] or "")


def _card(it: dict):
    legit, elig, urg = it["legitimacy"], it["eligible"], it["urgency"]
    with st.container(border=True):
        left, right = st.columns([5, 1])
        with left:
            st.markdown(f"**{it['title']}**")
            meta = [it.get("organisation") or "Unknown organisation", TYPE_NAMES.get(it["type"], it["type"]),
                    f"from {it['source']}"]
            if it.get("stipend_or_prize"):
                meta.append(it["stipend_or_prize"])
            st.caption(" · ".join(meta))
            tags = [f":{LEGIT_STYLE[legit['label']]}-background[{legit['label']}]"]
            tags.append(":green-background[Eligible]" if elig["ok"] else ":gray-background[Not eligible]")
            tags.append(f":{'gray' if urg['expired'] else 'violet'}-background[{urg['label']}]")
            if it.get("is_sample"):
                tags.append(":gray-background[Sample]")
            if it.get("also_seen_at"):
                tags.append(f":blue-background[Seen in {len(it['also_seen_at']) + 1} places]")
            st.markdown(" ".join(tags))
        right.metric("Score", it["total"], help="Provisional: legitimacy + urgency. Fit and value join when the Ranker ships.")
        with st.expander("Evidence and details"):
            if legit["red_flags"]:
                st.markdown("**Red flags found by the rules**")
                for f in legit["red_flags"]:
                    st.markdown(f"- **{f['label']}** — “{f['evidence']}”")
            st.markdown(f"**Eligibility:** {elig['reason']}")
            st.write(it.get("description") or "")
            if it.get("source_url"):
                st.markdown(f"[Open the source]({it['source_url']}) · fetched {str(it.get('fetched_at'))[:16].replace('T', ' ')}")
            for s in it.get("also_seen_at", []):
                st.caption(f"Also seen: {s['source']} {s.get('url') or ''}")


def results_page():
    _sidebar_status()
    st.title("Results")
    last = db.latest_run()
    if not last:
        st.info("No results yet. Run the agent first.")
        return
    items = db.run_items(last["id"])
    st.caption(f"From {last['id']} · {len(items)} opportunities · ranked by the Validator's rules "
               "(fit scoring arrives with the Ranker)")
    types = sorted({i["type"] for i in items})
    picked = st.multiselect("Type", types, default=types, format_func=lambda t: TYPE_NAMES.get(t, t))
    show_blocked = st.toggle("Show scams, expired and not-eligible items", value=True)
    for it in items:
        blocked = it["legitimacy"]["label"] == "Likely scam" or it["urgency"]["expired"] or not it["eligible"]["ok"]
        if it["type"] in picked and (show_blocked or not blocked):
            _card(it)


def profile_page():
    _sidebar_status()
    st.title("Profile")
    p = db.get_profile()
    if st.button("Use demo profile", icon=":material/person:"):
        db.save_profile(DEMO_PROFILE)
        db.audit(None, "Profile Agent", "demo profile loaded")
        st.rerun()
    with st.form("profile"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", p.get("name", ""))
        university = c2.text_input("University", p.get("university", ""))
        year = c1.selectbox("Year of study", [1, 2, 3, 4, 5], index=max(0, min(4, int(p.get("year", 1)) - 1)))
        branch = c2.text_input("Branch", p.get("branch", ""))
        cgpa = st.slider("CGPA range", 0.0, 10.0, (float(p.get("cgpa_min", 7.0)), float(p.get("cgpa_max", 8.0))), 0.1)
        skills = st.text_input("Skills (comma-separated)", ", ".join(p.get("skills", [])))
        interests = st.text_input("Interests (comma-separated)", ", ".join(p.get("interests", [])))
        goals = st.text_area("Goals", p.get("goals", ""))
        location = st.text_input("Location preference", p.get("location", ""))
        if st.form_submit_button("Save profile", type="primary"):
            split = lambda s: [x.strip() for x in s.split(",") if x.strip()]
            db.save_profile({"name": name, "university": university, "year": year, "branch": branch,
                             "cgpa_min": cgpa[0], "cgpa_max": cgpa[1], "skills": split(skills),
                             "interests": split(interests), "goals": goals, "location": location})
            db.audit(None, "Profile Agent", "profile saved", name)
            st.success("Profile saved. The next run uses it.")
    st.subheader("Profile memory")
    weights = db.get_weights()
    if weights:
        for t, w in sorted(weights.items(), key=lambda kv: -kv[1]):
            st.write(f"{TYPE_NAMES.get(t, t)}: weight {w:.2f}")
    else:
        st.caption("Nothing learned yet. Marking results Interested or Dismiss will teach the ranking.")


def audit_page():
    _sidebar_status()
    st.title("Audit log")
    st.caption("Every agent step, source fetched and decision, newest first.")
    rows = db.audit_rows()
    if rows:
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("Nothing logged yet.")
