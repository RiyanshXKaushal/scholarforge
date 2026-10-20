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

## Live app

**https://scholarforge.streamlit.app** (Streamlit Community Cloud, redeploys on every push to `main`).

## Configuration (Streamlit → Manage app → Settings → Secrets)

| Secret | Needed for | Required? |
| --- | --- | --- |
| `GEMINI_API_KEY` | Scout Planner and every LLM step | Yes. Without it the planner falls back to rules |
| `GEMINI_MODEL` | Choosing the Gemini model | No (default `gemini-flash-latest`) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | End-of-run digest to Telegram | Optional, but on for the demo |
| `GITHUB_TOKEN` | Higher GitHub search rate limit | Recommended. Shared servers can hit the anonymous limit |
| `N8N_WEBHOOK_URL` | Routing the digest through n8n instead | No |

Keys live only in Streamlit secrets. `.gitignore` excludes `secrets.toml`, and keys are never written to logs.

## Telegram digest

After every run, the app sends the top 3 actionable picks and the number of scams blocked straight to Telegram through the Bot API.

**Set-up:**
1. Create a bot with **@BotFather** (`/newbot`).
2. Send the bot one message.
3. Get your numeric ID from **@userinfobot**.
4. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` to secrets.

If a send fails, the reason appears in the Audit log under **Digest**.

**Optional n8n route:** `n8n/scholarforge_telegram_digest.json` is an importable workflow (webhook → format → Telegram). It is not used in the live app. It is only used if `N8N_WEBHOOK_URL` is set and the Telegram secrets are not, for teams that want to add more automation steps later.

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
| `core/digest.py` | Sends the end-of-run digest to Telegram (or to n8n if configured) |
| `core/db.py` | SQLite; rebuilt on every boot because Streamlit Cloud wipes local files |
| `data/seed_opportunities.json` | 10 tagged sample opportunities covering the test scenarios |
| `n8n/scholarforge_telegram_digest.json` | Optional n8n workflow (not used in the live app) |

## Status (Tue 20 Oct)

**Live and verified:**
- Profile page with a demo profile
- Gemini Scout Planner, with a rules fallback
- Live agent timeline
- Five scouts in parallel: GitHub, arXiv and Devpost (all real APIs), plus the sample library and Inbox
- Red-flag Validator with quoted evidence
- Eligibility, expiry and de-duplication
- Results cards and the audit log
- Telegram digest

**Next (Wed):**
- Gemini fit scoring in the Ranker (uses `RANKER_FIT`)
- Validator explanations (`VALIDATOR_EXPLAIN`)
- Opportunity detail page with the live tailored draft (`ACTION_DRAFT`)
- Approve / Reject risk tiers
- Faster Gemini calls

**Known limitations:**
- LinkedIn and X are not scraped by design (login walls, terms of service).
- Scores are provisional (legitimacy + urgency) until the Ranker ships.
- Items tagged **Sample** are realistic demo data, so every test scenario is reproducible.
