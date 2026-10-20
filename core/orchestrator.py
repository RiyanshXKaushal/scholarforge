"""Runs the agents in order. Scouts run in parallel; every step is reported to the UI
callback and persisted to run_steps + audit_log, including failures."""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from core import db, digest, validator
from core.profile import plan_searches
from core.scouts import SCOUTS, ScoutError


class NullUI:
    def start(self, step, label): pass
    def finish(self, step, ok, detail, items=0): pass


def run_agent(ui=None) -> dict:
    ui = ui or NullUI()
    run_id = "run-" + uuid.uuid4().hex[:6]
    db.create_run(run_id)
    db.audit(run_id, "Orchestrator", "run started")
    started = {}

    def begin(step, label):
        started[step] = (label, db.now_iso(), time.monotonic())
        db.save_step(run_id, step, label, "running", started[step][1])
        ui.start(step, label)

    def end(step, ok, detail, items=0):
        label, iso, t0 = started[step]
        detail = f"{detail} · {time.monotonic() - t0:.1f}s"
        db.save_step(run_id, step, label, "done" if ok else "failed", iso, items, detail)
        db.audit(run_id, label.split(" — ")[0], "done" if ok else "failed", detail)
        ui.finish(step, ok, detail, items)

    # 1. Profile Agent
    begin("profile", "Profile Agent — loading your profile and memory")
    profile = db.get_profile()
    weights = db.get_weights()
    end("profile", True, f"{profile.get('name')}, year {profile.get('year')} · "
                         f"{len(weights)} learned preferences")

    # 2. Scout Planner
    begin("planner", "Scout Planner — turning your profile into searches")
    plan, note = plan_searches(profile)
    end("planner", True, f"{note} GitHub: {', '.join(plan['github_languages'])} · arXiv: "
                         f"{' '.join(plan['arxiv_words'])} · Devpost: {', '.join(plan['devpost_keywords'])}")

    # 3. Scouts, in parallel
    found, failed = [], 0
    for step, label, _ in SCOUTS:
        begin(step, label)
    with ThreadPoolExecutor(max_workers=len(SCOUTS)) as pool:
        futures = {pool.submit(fn, plan, profile): step for step, _, fn in SCOUTS}
        for fut in as_completed(futures):
            step = futures[fut]
            try:
                items, detail = fut.result()
                found += items
                for it in items:
                    db.audit(run_id, "Scout", "fetched", f"{it.get('source')}: {it.get('source_url') or 'no link'}")
                end(step, True, detail, len(items))
            except ScoutError as e:
                failed += 1
                end(step, False, f"Failed: {e}")
            except Exception as e:  # never let one scout crash the run
                failed += 1
                end(step, False, f"Failed unexpectedly: {e.__class__.__name__}")

    # 4. Merge duplicates
    begin("dedupe", "Merging duplicates")
    items, merged = validator.dedupe(found)
    end("dedupe", True, f"{len(found)} found → {len(items)} unique ({merged} merged)", len(items))

    # 5. Validator (rules in code)
    begin("validator", "Validator — red-flag rules and eligibility")
    items = validator.assess(items, db.get_profile())
    scams = sum(i["legitimacy"]["label"] == "Likely scam" for i in items)
    ineligible = sum(not i["eligible"]["ok"] for i in items)
    expired = sum(i["urgency"]["expired"] for i in items)
    for i in items:
        if i["legitimacy"]["red_flags"]:
            db.audit(run_id, "Validator", i["legitimacy"]["label"],
                     f"{i['title']}: " + "; ".join(f["label"] for f in i["legitimacy"]["red_flags"]))
    end("validator", True, f"{scams} likely scams · {ineligible} not eligible · {expired} expired", len(items))

    db.save_items(run_id, items)

    # 6. Digest (Telegram via n8n) — skipped quietly if no webhook is configured
    sent, note = digest.send(run_id, profile, items)
    db.audit(run_id, "Digest", "sent" if sent else "skipped", note)

    status = "done" if failed == 0 else "done with failures"
    db.finish_run(run_id, status, plan)
    db.audit(run_id, "Orchestrator", "run finished", status)
    return {"run_id": run_id, "items": items, "failed_scouts": failed, "plan": plan}
