# ScholarForge

An autonomous opportunity agent for students, built for the Ziro Agentic AI Hackathon 2026 by Team Random.io.

Click **Run Agent** and watch the agents work live:

1. **Profile Agent** loads your profile and what it has learned.
2. **Scout Planner** turns the profile into searches. It uses Gemini, and falls back to rules if Gemini is unavailable.
3. **Scouts** search in parallel:
   - GitHub "good first issue"
   - arXiv research
   - Devpost hackathons
   - the tagged sample library
   - your forwarded Inbox
4. **Validator** applies red-flag rules and eligibility checks, written as code.
5. **Results** are ranked, with evidence for every flag.

A scout that fails is shown as failed with its reason. Nothing is invented.

## Run it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (Streamlit Community Cloud, free)

1. Push this folder to a GitHub repo, keeping the folder structure.
2. Go to share.streamlit.io, sign in with GitHub, and click **Create app**. Pick the repo, branch `main` and file `app.py`.
3. In the app's **Settings → Secrets**, paste the keys from `.streamlit/secrets.toml.example` with real values. Only `GEMINI_API_KEY` is needed for the LLM steps; the rest are optional.
4. Post the public URL in the team group. Every later push to `main` redeploys automatically.

Get a Gemini key at aistudio.google.com. Never commit it: `.gitignore` already excludes `secrets.toml`.

## Telegram digest (n8n)

1. In Telegram, message **@BotFather**, send `/newbot`, and copy the bot token.
2. Message your new bot once. Then get your chat ID from **@userinfobot**.
3. In n8n, import `n8n/scholarforge_telegram_digest.json`.
4. Open **Send to Telegram**: add a Telegram credential with the bot token, and replace `REPLACE_WITH_YOUR_CHAT_ID`.
5. Activate the workflow. Copy the **Production URL** of **Digest webhook** into the app's secrets as `N8N_WEBHOOK_URL`.

## Layout

| Path | What it is |
| --- | --- |
| `app.py` | Entry point and page navigation |
| `core/orchestrator.py` | Runs the agents in order, scouts in parallel, and logs every step |
| `core/profile.py` | Profile Agent, demo profile and Scout Planner |
| `core/scouts.py` | GitHub, arXiv, Devpost, sample and Inbox scouts |
| `core/validator.py` | Red-flag rules, eligibility, urgency and de-duplication (code, not LLM) |
| `core/prompts.py` | Every LLM prompt, including the ones the Wed/Thu features will use |
| `core/llm.py` | Gemini over REST in JSON mode |
| `core/digest.py` | Posts the end-of-run digest to n8n |
| `core/db.py` | SQLite; rebuilt on every boot because Streamlit Cloud wipes local files |
| `data/seed_opportunities.json` | 10 tagged sample opportunities covering the test scenarios |
| `n8n/scholarforge_telegram_digest.json` | Importable n8n workflow: webhook → format → Telegram |

## Status (Tue 20 Oct)

**Done:**
- Profile page with a demo profile
- Live agent timeline
- Parallel scouts
- Red-flag Validator with quoted evidence
- Eligibility, expiry and de-duplication
- Results cards
- Audit log
- Digest sender

**Next (Wed):**
- Gemini fit scoring in the Ranker (uses `RANKER_FIT`)
- Validator explanations (`VALIDATOR_EXPLAIN`)
- Opportunity detail page with the live tailored draft (`ACTION_DRAFT`)
- Risk tiers with Approve / Reject

**Known limitations:**
- LinkedIn and X are not scraped by design (login walls, terms of service).
- Scores are provisional (legitimacy + urgency) until the Ranker ships.
