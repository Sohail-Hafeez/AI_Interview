# AI Interview Platform (Recruitment Process Automation)

An AI-driven interview system built for the **Agents of SigNoz** hackathon. HR uploads a candidate spreadsheet, the system emails each candidate a unique interview link, candidates go through automated readiness checks (camera/face detection, speaker, microphone, network speed) and then a voice-based AI interview conducted and scored by an LLM. The entire pipeline is instrumented end-to-end with OpenTelemetry and observed via a self-hosted SigNoz instance (installed with Foundry).

This README is split into two halves on purpose: **Part 1** is what you need to get this running yourself. **Part 2** is the honest, blow-by-blow account of everything that broke while we built it, and exactly how we fixed each thing — because most of the real engineering here was in the debugging, not the happy path.

---

## Table of Contents

**Part 1 — Setup**

1. [Architecture Overview](#architecture-overview)
2. [Live Deployment](#live-deployment)
3. [Prerequisites](#prerequisites)
4. [Environment Variables](#environment-variables)
5. [Backend Setup (local)](#backend-setup-local)
6. [Frontend Setup (local)](#frontend-setup-local)
7. [Deploying It Yourself (Railway + Vercel)](#deploying-it-yourself-railway--vercel)
8. [SigNoz Setup (via Foundry)](#signoz-setup-via-foundry)
9. [Running Everything Together (local dev, with tracing)](#running-everything-together-local-dev-with-tracing)
10. [Observability: What's Instrumented](#observability-whats-instrumented)
11. [Reproducing the SigNoz Deployment](#reproducing-the-signoz-deployment)

**Part 2 — Struggles and Hardship** 12. [Why Two Laptops](#why-two-laptops) 13. [Every Issue We Hit, and How We Fixed It](#every-issue-we-hit-and-how-we-fixed-it)

**Reference** 14. [Project Structure](#project-structure)

---

## Architecture Overview

```
Candidate Sheet (Excel/CSV)
        │
        ▼
  HR Dashboard (React) ──upload──▶ FastAPI Backend ──▶ Supabase (Postgres)
                                        │
                                        ├──▶ MCP Email Server (subprocess) ──▶ SendGrid API
                                        │
                                        └──▶ Groq API (LLM + Whisper STT)

  Candidate Email ──opens link──▶ Interview Page (React)
                                        │
                    readiness checks: camera (face-api.js, client-side),
                    speaker test, mic check, network speed test
                                        │
                                        ▼
                              AI Interview Loop (voice Q&A)
                                        │
                                        ▼
                              Score + Summary written to DB

  FastAPI Backend ──OpenTelemetry (traces/logs)──▶ SigNoz (self-hosted via Foundry)
                                                          │
                                                          ├──▶ Dashboard
                                                          ├──▶ Alert ──▶ Slack
                                                          └──▶ SigNoz MCP server (dashboard/alert
                                                               provisioning via sync_alert_channel.py)
```

**Stack:**

- **Frontend:** React + TypeScript + Vite, deployed on **Vercel**
- **Backend:** FastAPI (Python), deployed on **Railway**
- **Database:** Supabase (Postgres) — not SQLite, to avoid data loss on redeploys
- **LLM + Speech-to-Text:** Groq API (Llama 3.1 for interview logic, Whisper for transcription)
- **Text-to-Speech:** Browser-native Web Speech API (client-side, picks best available female voice)
- **Face detection:** face-api.js (client-side, browser only)
- **Email:** SendGrid API via a custom **MCP server** (agent-style tool call, not a direct API call — see [Every Issue We Hit](#every-issue-we-hit-and-how-we-fixed-it) for why it's SendGrid and not the Gmail SMTP we started with)
- **Observability:** OpenTelemetry (traces, logs, custom spans) → SigNoz, self-hosted via **Foundry**; SigNoz's own MCP server is used to provision the Slack alert channel (`signoz/sync_alert_channel.py`)

---

## Live Deployment

- Frontend (Vercel):
- Backend (Railway):

The deployment is intentionally separate from the SigNoz observability proof — SigNoz runs self-hosted (see [SigNoz Setup](#signoz-setup-via-foundry)) and is not part of the public deployment.

---

## Prerequisites

- **Node.js** 18+ and npm
- **Python** 3.10+
- **Docker** with WSL2 (Windows) — see [SigNoz Setup](#signoz-setup-via-foundry) for the specific install method we used (native Docker Engine inside WSL2, **not** Docker Desktop — explained below)
- Accounts (all have free tiers):
  - [Groq](https://console.groq.com) — LLM + Whisper STT
  - [Supabase](https://supabase.com) — Postgres database
  - [SendGrid](https://sendgrid.com) — transactional email (Single Sender Verification is enough, no domain needed)
  - A Slack workspace (for alert notifications) — you need to be the **owner/admin** of the workspace to add an Incoming Webhook app; a public/community workspace you don't own won't work without admin approval
  - [Railway](https://railway.app) and [Vercel](https://vercel.com) accounts, if you want to deploy rather than just run locally

---

## Environment Variables

Create `backend/.env`:

```env
GROQ_API_KEY=your_groq_api_key
SENDGRID_API_KEY=your_sendgrid_api_key
GMAIL_ADDRESS=your_verified_sender@example.com   # must match a SendGrid Single Sender Verification
DATABASE_URL=postgresql://user:password@host:port/dbname   # Supabase connection string
FRONTEND_BASE_URL=http://localhost:5173

# Optional — only needed to run signoz/sync_alert_channel.py
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SIGNOZ_API_KEY=your_signoz_service_account_key
```

**Getting a SendGrid API key + verified sender:**

1. Create a free account at [sendgrid.com](https://sendgrid.com)
2. Settings → Sender Authentication → **Single Sender Verification** → verify the address you'll send from (this is the address you put in `GMAIL_ADDRESS` — the name is a holdover from the original Gmail-based implementation, it's really just "sender address" now)
3. Settings → API Keys → create a key with Mail Send permission, put it in `SENDGRID_API_KEY`

We didn't start here — see [Every Issue We Hit](#every-issue-we-hit-and-how-we-fixed-it) for why Gmail SMTP had to be replaced.

**Getting a Supabase connection string:**

1. Create a free project at [supabase.com](https://supabase.com)
2. Project Settings → Database → Connection string → use the **URI** format (the pooler connection, e.g. `aws-...pooler.supabase.com`)

Frontend (`frontend/.env`, optional — only needed if your backend isn't on `localhost:8000`):

```env
VITE_API_BASE=http://localhost:8000
```

---

## Backend Setup (local)

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

The backend auto-creates its database tables on startup (`db.init_db()`), so no manual migration step is needed once `DATABASE_URL` is set.

---

## Frontend Setup (local)

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` — this is the HR Dashboard. Interview links look like `http://localhost:5173/interview/<token>`.

---

## Deploying It Yourself (Railway + Vercel)

### Backend → Railway

1. New Project → Deploy from GitHub repo
2. Set **Root Directory** to `backend`
3. Railway auto-detects the `Procfile` (`web: opentelemetry-instrument uvicorn main:app --host 0.0.0.0 --port $PORT`) via its Railpack builder
4. Variables tab → add every key from [Environment Variables](#environment-variables) above (`GROQ_API_KEY`, `SENDGRID_API_KEY`, `GMAIL_ADDRESS`, `DATABASE_URL`, `FRONTEND_BASE_URL`)
5. `FRONTEND_BASE_URL` must be the **real deployed Vercel URL**, not `localhost` — the backend's CORS allow-list checks against it exactly (see the CORS bug in [Every Issue We Hit](#every-issue-we-hit-and-how-we-fixed-it))
6. Deploy, then copy the generated Railway URL

### Frontend → Vercel

1. New Project → import the GitHub repo
2. Set **Root Directory** to `frontend`
3. Add environment variable `VITE_API_BASE` = your Railway backend URL
4. `frontend/vercel.json` (already in this repo) rewrites all routes to `/index.html` so client-side routes like `/interview/<token>` don't 404 on refresh
5. Deploy, then update `FRONTEND_BASE_URL` on Railway to this Vercel URL (chicken-and-egg: deploy backend first with a placeholder, deploy frontend, then update the backend variable once you know the real Vercel URL)

Note that the Procfile wraps the app with `opentelemetry-instrument`. Without an `OTEL_EXPORTER_OTLP_ENDPOINT` variable set on Railway, the OTel SDK just retries the export in the background and gives up quietly — it does not block or crash the app. Point it at your SigNoz instance's OTLP endpoint only if that instance is reachable from Railway's network (our self-hosted SigNoz was local-only, so in this deployment traces are demonstrated separately, not shipped from the live Railway instance).

---

## SigNoz Setup (via Foundry)

We run SigNoz via **Foundry** inside **WSL2**, using **native Docker Engine** — deliberately **not** Docker Desktop. Docker Desktop's WSL2 integration caused ClickHouse to crash on startup in our testing; native Docker Engine installed directly inside the WSL2 distro avoided this entirely.

### 1. Install Docker natively inside WSL2

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Close and reopen your WSL terminal, then verify:

```bash
docker ps
```

This should return an empty table (no error) — no `sudo` required.

If you already have Docker Desktop installed, we recommend uninstalling it entirely for this setup (Windows Settings → Apps) to avoid any WSL-integration conflicts. Docker Desktop is not required — WSL2 + native Docker Engine is a fully standalone setup.

### 2. Install Foundry

```bash
curl -fsSL https://signoz.io/foundry.sh | bash
```

If `foundryctl` isn't found afterward, it's likely a PATH issue:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
foundryctl version
```

### 3. Use `signoz/casting.yaml`

This repo already includes a working `signoz/casting.yaml` and `signoz/casting.yaml.lock` — copy them into `~/signoz/` on your machine, or use the ones in this repo directly:

```bash
mkdir -p ~/signoz && cd ~/signoz
```

```yaml
apiVersion: v1alpha1
kind: Installation
metadata:
  name: signoz
spec:
  deployment:
    flavor: compose
    mode: docker
  mcp:
    spec:
      enabled: true # also stands up SigNoz's own MCP server, used by sync_alert_channel.py
```

### 4. Deploy

```bash
foundryctl cast -f casting.yaml
```

This pulls and starts all SigNoz containers (ClickHouse, OTel Collector, Query Service, Frontend, Postgres metastore, MCP server, etc.) — takes a few minutes on first run.

**If this fails with `"signal: killed"`** — that's the Linux OOM killer, not a real error. WSL2 caps its memory (roughly half your host RAM by default), and pulling several large images concurrently can exceed that. Fix: create/edit `C:\Users\<you>\.wslconfig` on the **Windows** side:

```ini
[wsl2]
memory=6GB
processors=4
```

Then from Windows PowerShell: `wsl --shutdown`, reopen WSL, and retry `foundryctl cast -f casting.yaml`.

### 5. Verify

```bash
docker ps
```

All containers should show `Running` or `Healthy`, except `signoz-telemetrystore-clickhouse-user-scripts`, which is expected to show `Exited` — it's a one-time init script, not a crash.

Open `http://localhost:8080` — you should see the SigNoz sign-up screen. Create an admin account.

### 6. Sync the Slack alert channel (optional)

```bash
python signoz/sync_alert_channel.py --dry-run   # preview
python signoz/sync_alert_channel.py             # apply
```

This reads `SLACK_WEBHOOK_URL` and `SIGNOZ_API_KEY` from `backend/.env` and creates/updates the `ai-interview-slack` notification channel via SigNoz's own MCP server — keeping the webhook credential in the gitignored `.env` rather than in the git-tracked `casting.yaml`.

---

## Running Everything Together (local dev, with tracing)

**Backend** (with OpenTelemetry instrumentation):

```powershell
cd backend
.\venv\Scripts\Activate.ps1
$env:OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"
$env:OTEL_SERVICE_NAME="ai-interview-backend"
opentelemetry-instrument python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

If your app and SigNoz run on **different machines**, see [Why Two Laptops](#why-two-laptops) for the cross-machine networking setup — `OTEL_EXPORTER_OTLP_ENDPOINT` then needs to point at the other machine's IP instead of `localhost`.

**Frontend:**

```powershell
cd frontend
npm run dev
```

Open `http://localhost:5173`, upload a candidate sheet (columns: `Name`, `Email`, `Role`), and open the emailed interview link.

---

## Observability: What's Instrumented

- **Custom spans** (in `backend/main.py`):
  - `llm.ask` — every Groq LLM call, tagged with `llm.model`, `llm.attempts`, `llm.malformed_json_retries`
  - `stt.transcribe` — every Whisper transcription call, tagged with `interview.token`, `check.type` (`mic_check`, `interview_answer`), `transcript.length`
  - `email.send_invite` — every candidate invite email, tagged with `interview.role`, `email.sent`
  - Interview-level attributes added to the relevant HTTP request spans: `interview.token`, `interview.role`, `interview.question_number`, `interview.final_score`, `disqualify.reason`, `check.type` for speaker/network checks
- **Structured logs** (OTLP-exported via Python's `logging` module, `app_logger` at INFO with root kept at WARNING to cut noise — see the logging bug below):
  - Interview started / completed (with score)
  - Candidate disqualified (with reason)
  - Email sent / failed
  - LLM malformed-JSON retry attempts and exhaustion
- **Dashboards** (`signoz/dashboard.json` and `signoz/dashboard-ai-interview.json`, importable into SigNoz): LLM latency (P90), STT latency (P90), LLM retry count, interview outcomes (completed vs. disqualified), email delivery success/failure, application log activity by severity
- **Alert**: fires when a candidate is disqualified (2+ faces detected, or manually flagged), delivered via a Slack Incoming Webhook, provisioned via `signoz/sync_alert_channel.py`

---

## Reproducing the SigNoz Deployment

Judges/reviewers: `signoz/casting.yaml` and `signoz/casting.yaml.lock` in this repo describe the exact Foundry-based SigNoz installation used for this project.

```bash
mkdir -p ~/signoz-repro && cd ~/signoz-repro
# copy casting.yaml and casting.yaml.lock from this repo into this folder
foundryctl cast -f casting.yaml
```

This reproduces the **installation** (same SigNoz version, same component topology, MCP server enabled) on your own machine — it does **not** come pre-loaded with our dashboard, alert, or historical trace data, since those are runtime state stored inside a running instance's database, not part of the install recipe. To see the dashboards, import `signoz/dashboard.json` and/or `signoz/dashboard-ai-interview.json` via SigNoz's dashboard import feature. To see live traces/logs, run this repo's backend yourself, pointed at your freshly-reproduced instance's OTLP endpoint (`http://localhost:4317` if on the same machine), and exercise the app (upload a sheet, do an interview).

---

## Why Two Laptops

This project was built and instrumented across **two physical machines**, and we're documenting this openly because it directly affects how you reproduce parts of this setup.

- **Laptop A** ("i3 laptop" in commit history/discussion): an older machine (3rd-gen Intel i3, very limited free disk space). Used for all **application development** — the FastAPI backend and React frontend. This is intentionally lightweight: no local LLM, no local Whisper, no Docker required, since Groq/Supabase/SendGrid handle the heavy lifting in the cloud.
- **Laptop B** ("i5 laptop"): a newer machine (6th/7th-gen Intel i5, 8GB RAM, 256GB SSD). Used exclusively to run **Docker + the self-hosted SigNoz stack** (via Foundry), because SigNoz's stack (ClickHouse, OTel Collector, Query Service, etc.) needs real RAM and disk headroom that Laptop A did not have.

The two laptops were connected via **Laptop B's mobile hotspot** (Laptop A connected as a hotspot client). This means:

- Laptop A's backend sends traces/logs to Laptop B's SigNoz instance over the hotspot's local network, not `localhost`.
- This introduced real networking friction (documented in detail below) that you will **not** need to deal with if you run everything on a single machine.

**If you're reproducing this on one machine**, just point `OTEL_EXPORTER_OTLP_ENDPOINT` at `http://localhost:4317` and everything works without any port-forwarding or firewall configuration.

Later in the project, a teammate independently set up the SigNoz dashboards, alert rules, and MCP integration on a **third laptop** (an i7) while the deployment work above continued on Laptops A/B — see the note on merging that work at the end of [Every Issue We Hit](#every-issue-we-hit-and-how-we-fixed-it).

---

## Every Issue We Hit, and How We Fixed It

This section is intentionally detailed — if you hit the same thing, you shouldn't have to debug it from scratch like we did.

### Application bugs

| Issue                                                                                       | Cause                                                                                                                                                                                                                    | Fix                                                                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Upload silently did nothing (`Failed to fetch`)                                             | Missing `catch` block around a `fetch()` call — network-level failures (backend not running, CORS block) weren't being caught, only HTTP-level errors were                                                               | Added a proper `catch` block that surfaces the actual error via a toast/alert                                                                                                                                            |
| `pandas.read_excel` raised `"Excel file format cannot be determined"`                       | Reading from an in-memory `BytesIO` buffer doesn't let pandas auto-sniff the engine from a file extension                                                                                                                | Explicitly pass `engine="openpyxl"`                                                                                                                                                                                      |
| `zipfile.BadZipFile: File is not a zip file`                                                | The uploaded "`.xlsx`" file was actually plain tab-separated text with a renamed extension (common if someone copy-pastes into a text editor and saves with the wrong extension)                                         | Added a fallback: if `read_excel` fails, retry with `pd.read_csv(..., sep=None, engine="python")` to auto-detect delimiter                                                                                               |
| React crashed with `"Objects are not valid as a React child"`                               | The LLM occasionally nested its JSON response (e.g. returned `{"next_question": {"question": "..."}}` instead of a plain string), because the conversation history mixed two different expected JSON shapes across turns | Added a `to_text()` normalizer that unwraps nested dicts to a string before sending to the frontend                                                                                                                      |
| Text-to-speech only spoke once per session                                                  | `pyttsx3`'s SAPI5 engine on Windows gets stuck after one `runAndWait()` call if reused across multiple calls                                                                                                             | Create a fresh `pyttsx3.init()` engine instance on every `speak()` call instead of reusing one global instance                                                                                                           |
| `OpenTelemetry` warning spam: `"Overriding of current LoggerProvider is not allowed"`       | `opentelemetry-instrument` (the CLI auto-instrumentation wrapper) already registers a global `LoggerProvider`; our code then tried to register a second one, which the SDK correctly refuses                             | Removed our manual `set_logger_provider()` call — we pass our `LoggerProvider` directly to `LoggingHandler`, so global registration isn't actually needed for our own export to work                                     |
| Duplicate log/trace entries, and later, too much log volume                                 | `opentelemetry-instrument`'s own auto-instrumentation and our manual logging handler both attach to the root logger; with root left at INFO, library/SDK internals made up half of every exported log batch              | Kept root logger at WARNING, silenced known-noisy loggers (`opentelemetry.exporter.otlp...`, `httpx`, `mcp.server.lowlevel.server`) explicitly, and log our own business events through a dedicated `app_logger` at INFO |
| `tsc` build failed on Vercel: `Type '() => boolean' is not assignable to type '(() => void) | undefined'`                                                                                                                                                                                                              | A `useEffect` cleanup function returned `listeners.delete(listener)` directly, whose return type is `boolean` — not a valid cleanup return type                                                                          | Wrapped the call in braces (`() => { listeners.delete(listener) }`) so the arrow function returns `void` |

### Environment / tooling bugs

| Issue                                                                     | Cause                                                                                                                                                                                                                                                                                                                   | Fix                                                                                                                                                                                     |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pip install` failed with `"Fatal error in launcher... cannot find file"` | The virtual environment was originally created at one path, then the whole project folder was moved/renamed afterward. Windows venv launchers (`pip.exe` and other console-script `.exe` files) bake in an **absolute path** to `python.exe` at creation time — moving the folder breaks that embedded path permanently | Recreate the venv fresh, directly in its final location (`Remove-Item -Recurse -Force venv` then `python -m venv venv`), rather than trying to move an existing one                     |
| `rmdir /s /q venv` did nothing, no error shown                            | `rmdir /s /q` is `cmd.exe` syntax, not valid PowerShell — PowerShell's `rmdir` is an alias for `Remove-Item`, which doesn't accept those flags and silently failed to parse                                                                                                                                             | Use `Remove-Item -Recurse -Force venv` instead                                                                                                                                          |
| Confusing "no traces" debugging turned out to be multiple stray processes | Across many restarts (fixing bugs, changing ports), several old backend processes were still running in the background — including a leftover process from an entirely different project folder — and it wasn't obvious which one was actually serving traffic                                                          | Used `Get-NetTCPConnection`/`Get-Process` to identify exactly which PID owned which port, killed all stray Python processes, and restarted exactly one clean instance before re-testing |

### SigNoz / Foundry bugs

| Issue                                                                                        | Cause                                                                                                                                                                                                                                                               | Fix                                                                                                                                                                                                             |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `foundryctl cast -f casting.yaml` failed with `{"exception": {"message": "signal: killed"}}` | WSL2's default memory cap (~half of host RAM) was exceeded while pulling multiple large container images concurrently and starting ClickHouse — the Linux OOM killer terminated the process                                                                         | Increased WSL2's memory allocation via `.wslconfig` (see [SigNoz Setup](#signoz-setup-via-foundry))                                                                                                             |
| Docker Desktop + WSL2 caused ClickHouse container crashes                                    | Documented conflict between Docker Desktop's WSL integration and SigNoz's ClickHouse container                                                                                                                                                                      | Uninstalled Docker Desktop entirely, installed Docker Engine natively inside WSL2 instead                                                                                                                       |
| Traces never reached SigNoz from the other laptop                                            | WSL2 only forwards `localhost` traffic by default, not traffic arriving at other network interfaces                                                                                                                                                                 | Set up `netsh interface portproxy` to bridge external traffic into WSL2 (firewall rules for ports 4317/4318, then `netsh interface portproxy add v4tov4` pointing at WSL2's internal IP from `wsl hostname -I`) |
| Port-forwarding set up correctly, but still no connection                                    | Used the SigNoz machine's **real Wi-Fi IP** (`192.168.0.132`) as the endpoint, but the two laptops were actually connected via **mobile hotspot**, a completely different subnet (`192.168.137.x`) — so the two machines weren't on the same network segment at all | Identified this via `Test-NetConnection`'s `SourceAddress` field showing the calling machine's actual subnet, then switched to the hotspot-facing IP (`192.168.137.1`) instead                                  |
| SigNoz dashboard panel showed "No Data" with an aggregate on `duration`                      | The correct field name in this SigNoz version is `duration_nano`, not `duration`                                                                                                                                                                                    | Select `duration_nano` explicitly when configuring a panel's aggregate                                                                                                                                          |
| Boolean attribute filters (`interview.completed = true`) returned no data                    | Depending on how the attribute was recorded, SigNoz's query parser sometimes expects the value quoted (`= 'true'`) and sometimes unquoted (`= true`)                                                                                                                | Try both forms if a boolean filter unexpectedly returns no data                                                                                                                                                 |
| Alert rule wouldn't save: `"Please select at least one channel for each threshold"`          | SigNoz requires a notification channel attached before an alert rule can be saved — there's no way to save a channel-less rule                                                                                                                                      | Created a Slack Incoming Webhook and attached it as a channel (later automated via `signoz/sync_alert_channel.py`)                                                                                              |
| Slack app creation loop: kept bouncing back to the sign-in screen                            | Tried creating the Slack app inside a workspace we weren't an admin of (a public/community workspace), which requires admin approval and has no "sign in to create" path from that screen                                                                           | Created a brand-new personal Slack workspace at [slack.com/get-started](https://slack.com/get-started) first (where we're automatically the owner), then created the app inside that workspace                  |
| Alert fired ~1-2 minutes after the actual event                                              | SigNoz evaluates alert rules on a periodic interval, not instantly on ingestion                                                                                                                                                                                     | Expected behavior, not a bug — just don't expect instant delivery                                                                                                                                               |

### Deployment bugs — the email saga and friends

Getting emails to actually arrive in production was the single most time-consuming bug of the whole project, because it was really **three separate bugs stacked on top of each other**, each one masking the next:

| Issue                                                                                        | Cause                                                                                                                                                                                                                                                                                                                                                                                       | Fix                                                                                                                                                                    |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Emails "sent" but candidates never received them — not even in spam                          | Gmail SMTP silently dropped messages sent from a personal Gmail account via an unfamiliar cloud IP (Railway's outbound IP) — Google's anti-abuse heuristics reject/drop with no bounce and no visible error                                                                                                                                                                                 | Switched sending from Gmail SMTP to the SendGrid API, which is designed for exactly this (sending transactional email from application servers)                        |
| Even after switching providers, some sends still silently "succeeded" while actually failing | The MCP client never checked `result.isError` on the tool call result — MCP reports tool-level failures as a normal-looking result object with `isError=True`, not by raising an exception, so a failed `send_email` call looked identical to a successful one                                                                                                                              | Added a check that reads `result.isError` and raises a `RuntimeError` with the actual error detail if it's set                                                         |
| Locally everything worked; on Railway, sends failed with missing-credentials errors          | `StdioServerParameters(env=None)` does not inherit the parent process's environment — the MCP SDK passes only a minimal safe subset to the subprocess it spawns. Locally the email server subprocess still found `SENDGRID_API_KEY`/`GMAIL_ADDRESS` via its own `.env` file, but Railway's container has no `.env` file, only injected environment variables, so the subprocess had nothing | Passed `env=dict(os.environ)` explicitly to `StdioServerParameters` so the subprocess inherits everything the parent process has                                       |
| Railway's own logs showed nothing useful while debugging the above                           | Our OTel logging setup only exported logs to SigNoz, which wasn't reachable from Railway, so errors had nowhere visible to go                                                                                                                                                                                                                                                               | Added a plain `logging.StreamHandler()` on the root logger so errors also print straight to stdout/Railway's log viewer, independent of whether OTLP export is working |
| Interview links returned Vercel's `404: NOT_FOUND`                                           | Vercel serves a static build; without a rewrite rule, opening a client-side route directly (e.g. `/interview/<token>`) requests a file that doesn't exist on the CDN — only `/` does                                                                                                                                                                                                        | Added `frontend/vercel.json` with a catch-all rewrite to `/index.html` so React Router handles the route client-side                                                   |
| Frontend deployed fine, but every API call failed due to CORS                                | `FRONTEND_BASE_URL` on Railway was still set to `http://localhost:5173` from local dev, so the backend's CORS allow-list didn't include the real Vercel origin                                                                                                                                                                                                                              | Updated the `FRONTEND_BASE_URL` environment variable on Railway to the actual deployed Vercel URL                                                                      |
| A teammate's pull request accidentally included a compiled `signoz/__pycache__/*.pyc` file   | `.gitignore` only excluded `backend/__pycache__/`, not `__pycache__` directories anywhere else in the repo                                                                                                                                                                                                                                                                                  | Removed the file from the merge with `git reset`, deleted it, and widened `.gitignore` to `**/__pycache__/` and `*.pyc`                                                |

**On merging independent work:** partway through, a teammate cloned the repo onto a third (i7) laptop and independently built out the SigNoz dashboards, alert rules, and MCP server integration (`signoz/sync_alert_channel.py`, the MCP-enabled `casting.yaml`, a freshly re-exported dashboard) while deployment work continued in parallel on the original two laptops. Their branch was reviewed file-by-file for conflicts against the live deployment, then merged in with a single squash commit — keeping one working deployment with all the observability tooling folded in, rather than two diverging copies of the project.

### A note on reproducibility scope

`casting.yaml`/`casting.yaml.lock` reproduce the **SigNoz installation only** — not the dashboards, alert rule, notification channel, or historical trace/log data, which live in the running instance's own database. We've exported the dashboards as JSON (`signoz/dashboard.json`, `signoz/dashboard-ai-interview.json`) so they can be re-imported, and `signoz/sync_alert_channel.py` reproduces the Slack notification channel via SigNoz's MCP server — but the alert rules themselves currently only exist as documented/screenshotted proof (see the project's submission write-up) rather than as a reproducible artifact, since SigNoz doesn't offer a clean export mechanism for alert rules at this time.

---

## Project Structure

```
HR/
├── backend/
│   ├── main.py                  # FastAPI app, all routes, OTel instrumentation
│   ├── db.py                    # Postgres (Supabase) data access layer
│   ├── email_mcp_server.py       # MCP server exposing a send_email tool (SendGrid API)
│   ├── mcp_email_client.py       # MCP client helper used by main.py
│   ├── requirements.txt
│   └── Procfile                  # opentelemetry-instrument + uvicorn, for Railway
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── HRDashboard.tsx   # upload sheet, view results, download export
│   │   │   └── InterviewPage.tsx # candidate-facing flow: checks + interview loop
│   │   ├── components/
│   │   └── App.tsx               # routing
│   ├── vercel.json               # SPA rewrite so client-side routes don't 404
│   └── package.json
├── signoz/
│   ├── casting.yaml               # Foundry deployment recipe (MCP server enabled)
│   ├── casting.yaml.lock          # pinned versions/config for reproducibility
│   ├── dashboard.json             # exported SigNoz dashboard, importable
│   ├── dashboard-ai-interview.json # second exported dashboard, importable
│   └── sync_alert_channel.py      # provisions the Slack notification channel via SigNoz's MCP server
├── Dockerfile                     # alternative single-container deployment path
├── docker-compose.app.yml         # alternative single-container deployment path
└── .dockerignore
```

## As mentioned in the rules we are acknowledging the use of AI Tools

During the Hackathon the project was build by the help of claude code and blog was written with the assistance of ChatGPT
