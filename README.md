# Badi eSIM support ticketing

React + TypeScript + Vite frontend, with a FastAPI and PostgreSQL backend.

Customers start a guided chat, receive an automatically generated ticket summary, join a durable T1 queue, exchange live replies, and follow their case status. The agent workspace provides a live queue, search and filters, conversations, public replies, private notes, assignment, status/priority controls, and audit history. PostgreSQL stores the persistent data; Docker runs the database while FastAPI and Vite run locally.

## Page map

- Customer: `#/` -> `#/support` -> guided email/category/issue intake -> generated summary -> T1 queue -> live conversation. Existing tickets use private access.
- Agent: open `#/agent` directly -> sign in -> filtered live queue -> conversation and case controls.

Public navigation has no staff link. Staff sign in at `#/agent`; SQL roles
select the operator desk or TEAM_LEAD monitoring view. Both are area-scoped.
The leader can monitor and emergency-close with an audit reason, but cannot
send replies or notes. See the [permissions and session guide](docs/staff-and-support.md).

## Docker PostgreSQL setup (recommended)

Docker runs only PostgreSQL in this step. FastAPI and Vite still run locally so
their code is easy to edit and debug.

First install Docker Desktop using the WSL 2 backend. If Windows says Virtual
Machine Platform is disabled, open PowerShell **as Administrator**, navigate to
this project, and run the helper below. It enables the Windows features and
installs WSL, but never restarts your computer automatically.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/enable-docker-windows.ps1
```

Save your work and restart Windows if requested. Then, in normal PowerShell:

```powershell
winget install --id Docker.DockerDesktop --exact --source winget --override "install --user --quiet --accept-license --backend=wsl-2"
```

Open Docker Desktop and wait until its engine is running. Docker Hub sign-in is
not needed for this project's public PostgreSQL image.

For a fresh checkout, install the frontend/Python dependencies first:

```powershell
npm.cmd install
py -3.13 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
```

Start and initialize the Docker database:

```powershell
backend/.venv/Scripts/python.exe backend/docker_database.py setup
```

If your terminal reports Python is not found, use **Windows PowerShell** and
the project launcher. It calls the virtual environment's Python directly:

```powershell
Set-Location C:\Users\Lenovo\Badi-Ticketing
.\scripts\database.ps1 setup
```

The launcher also accepts `start`, `stop`, `status`, and `prepare`.

The helper creates random passwords in the ignored root `.env`, starts the
PostgreSQL container, waits for its health check, applies migrations, and seeds
demo tickets. Only after these succeed does it update `backend/.env` to use
`127.0.0.1:55433`. Restart FastAPI after that switch.

The Docker database starts with fresh demo data; existing tickets in the old
Windows database are not copied. The old files remain intact in
`.local/postgres-data`, and the previous backend settings are backed up to
`.local/backend-before-docker.env`. The demo agent credentials remain in
`.local/agent-credentials.txt`.

Daily database commands from the project root:

```powershell
backend/.venv/Scripts/python.exe backend/docker_database.py start
backend/.venv/Scripts/python.exe backend/docker_database.py status
backend/.venv/Scripts/python.exe backend/docker_database.py stop
```

After initial setup, the equivalent Compose commands are `docker compose up -d
--wait db`, `docker compose ps`, and `docker compose stop db`. Run them from the
project root. Use `docker compose logs --tail=50 db` to inspect database errors.

`compose.yaml` defines the service, loopback-only port, health check, and named
volume. The persistent data lives in Docker volume
`badi-ticketing_postgres_data`. `docker compose down` keeps that volume;
`docker compose down -v` **deletes it and all Docker database data**. Keep the
root `.env` because changing its passwords does not change an existing database
volume's passwords.

The init script `docker/postgres/init-app.sh` runs only for a new volume. It
creates the normal `badi` login and its database; FastAPI does not connect as
the PostgreSQL superuser. Alembic handles application schema changes separately.

To prepare configuration without starting Docker or switching the working API:

```powershell
backend/.venv/Scripts/python.exe backend/docker_database.py prepare
```

## Alternative Windows setup without Docker

Run these commands in PowerShell from the project root. Python 3.13+ is required.

```powershell
npm.cmd install
py -3.13 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements-lock.txt
backend/.venv/Scripts/python.exe backend/dev_database.py setup
```

The setup helper downloads PostgreSQL 17 Windows binaries from EDB, initializes a database listening only on `127.0.0.1:55432`, creates a normal application database user, runs the Alembic migration, and inserts three demo tickets. It does not install a Windows service or require Docker. Rerunning setup preserves existing data and avoids duplicate seeds.

Local files:

- `backend/.env`: generated database connection settings.
- `.local/agent-credentials.txt`: demo agent email and random password. Open locally to sign in; do not commit or share it.
- `.local/postgres-data`: persistent database files. Stopping the server does not erase them.
- `.local/postgres.log`: database log.

These paths and the Python environment are ignored by Git. Keep the database data directory intact while PostgreSQL is running.

## Run locally

Start the database again after a reboot (choose the command for your setup):

```powershell
# Docker PostgreSQL:
backend/.venv/Scripts/python.exe backend/docker_database.py start

# Or the original portable Windows PostgreSQL:
backend/.venv/Scripts/python.exe backend/dev_database.py start
```

In one terminal, run the API:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-proxy-headers --reload
```

In another terminal, run the frontend:

```powershell
npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Visit `http://127.0.0.1:5173/` for the homepage. Open `http://127.0.0.1:5173/#/agent` directly for agent sign-in. Use the credentials in `.local/agent-credentials.txt`. Refreshing preserves the eight-hour session; signing out revokes it immediately on the server.

Vite is configured to use port 5173 with `strictPort`, so it refuses a busy port
instead of silently switching. Use one Vite instance and open
`http://localhost:5173` (or `http://127.0.0.1:5173`). If the server is already
running, reuse that address instead of starting another instance on 5174.

The earlier “Request origin is not allowed” error came from running the page
on port 5174 while the API allowed only 5173. The CSRF middleware rejects that
POST before it reaches a route or SQL. This is an origin mismatch, not a SQL
permission error. Other origins remain blocked. For an intentional deployment
address change, configure its exact origin in `backend/.env` and restart FastAPI.

Stop the foreground servers with Ctrl+C. Stop the database for your chosen setup:

```powershell
backend/.venv/Scripts/python.exe backend/docker_database.py stop
# Or, for the original portable database:
backend/.venv/Scripts/python.exe backend/dev_database.py stop
```

## Use an existing PostgreSQL server instead

Skip the local database helper. Create an empty database owned by a normal login role, copy `backend/.env.example` to `backend/.env`, and set `DATABASE_URL` to your connection. Do not commit the actual password.

```powershell
backend/.venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
Push-Location backend
.venv/Scripts/python.exe -m app.seed
Pop-Location
```

The seed command prompts for a 12-character-or-longer demo agent password. It only creates the account if it does not already exist; rerunning it does not reset passwords.

## Guided chat and routing flow

See [the flowchart and routing guide](docs/chat-routing.md) for the full flow,
agent eligibility, capacity rules, and local sample-account reset instructions.

## Follow the code

| File | Responsibility |
| --- | --- |
| `src/App.tsx` | Hash routes and public navigation; no public agent link |
| `src/pages/SupportPage.tsx` | Customer creation, private ticket return, and chat |
| `src/pages/AgentPage.tsx` | Agent authentication |
| `src/pages/AgentWorkspace.tsx` | Queue, filters, conversation selection, case controls, and audit display |
| `src/components/ChatThread.tsx` | Shared message bubbles, timestamps, public/private composers, and draft handling |
| `src/components/GuidedIntake.tsx` | Customer questions and generated-summary review |
| `src/components/CustomerBot.tsx` | New help and private-code recovery inside the bot |
| `src/components/FaqPanel.tsx` | Searchable reviewed Badi FAQ revision |
| `src/components/TicketForm.tsx` | Agent-only manual creation form |
| `src/components/StaffAccountMenu.tsx` | Avatar menu for availability, capacity and sign-out |
| `src/pages/FaqPage.tsx` | Separate FAQ route |
| `src/hooks/useLiveQuery.ts` | Initial access check, SSE connection, and automatic reconnect |
| `src/api.ts` | TypeScript data types and HTTP request helper |
| `backend/app/ticket_routes.py` | Ticket, message, management, customer-access, and stream endpoints |
| `backend/app/conversations.py` | Database operations and separate agent/customer response builders |
| `backend/app/live.py` | Server-Sent Events snapshots |
| `backend/app/intake.py` | Local extractive issue summaries |
| `backend/app/routing.py` | FIFO pool, least-loaded dispatch, and transaction locking |
| `backend/app/queue_worker.py` | SQL queue retry every two seconds |
| `backend/app/demo_accounts.py` | Explicit local sample-account reset |
| `backend/app/security.py` | Agent password/session verification |
| `backend/app/models.py` | SQLAlchemy tables |
| `backend/migrations/versions/0002_conversations.py` | Chat/access/audit schema and existing-description backfill |
| `compose.yaml` | PostgreSQL container, health check, loopback port, and persistent volume |

The code has comments and blank lines around the important boundaries. A small
UI edit to try: change the composer guidance in `ChatThread.tsx`, or the empty
queue message in `AgentWorkspace.tsx`.

## Test the customer and agent together

1. Open `http://127.0.0.1:5173/`, click Contact Support, then Start a chat. Answer email, category, issue description, and optional order ID; confirm the generated summary.
2. Save the generated ticket number and private access code. You can download
   them as a text file. Keep that file private: the code unlocks the case.
3. Open a separate private browser window at
   `http://127.0.0.1:5173/#/agent`. Sign in with
   `.local/agent-credentials.txt` and select the new ticket.
4. Check automatic T1 assignment, or waiting position when agents are busy. Send replies from each window. They should appear on the other side in
   approximately one second, without refreshing either page.
5. Add an internal note as the agent. It must appear only in the agent window.
6. Change status, priority, or assignment. Inspect the activity history.
7. Start another chat and tell the assistant you have a ticket code. Active cases resume; completed ones offer history. A valid cookie restores the case automatically on refresh.
8. Try a phone-sized window, or temporarily take the customer browser offline
   and reconnect. The current history reloads automatically.

The sample logins are `agent@example.com` (Badi Support) and
`lead@example.com` (TEAM_LEAD), using the existing local password in
`.local/agent-credentials.txt`. Mia was consolidated into Badi Support;
the Mia login is retired. Transfer actions support additional operator accounts
when they are added. See [the staff guide](docs/staff-and-support.md#account-menu-handoff-and-reset)
for availability, handoff, five-minute return cooldowns, and the explicit local
test-data reset.

## Where data lives and what a click does

- **New customer chat:** `GuidedIntake` asks questions and previews a local
  extractive summary. It submits only the customer's answers; FastAPI generates
  the subject and OPEN / MEDIUM workflow values, then attempts T1 routing.
  Agent-created tickets still use `TicketForm`. One transaction creates the
  PostgreSQL ticket, initial public message, creation and routing events. A
  PostgreSQL identity generates the readable `BD-1001` number; new status is
  `OPEN`. Existing descriptions were preserved as initial messages by migration.
- **Returning customer:** a remembered cookie restores the case automatically.
  Otherwise the bot asks for a private access code. Only its SHA-256 hash is
  stored in PostgreSQL; email and ticket numbers alone do not unlock a case.
  The browser receives an HttpOnly, SameSite=Strict cookie for that ticket.
  The raw code is shown at creation and is never included in a URL or stored
  in localStorage. Email alone cannot grant ticket access. The remembered
  browser cookie lasts 30 days; the saved code is the return credential.
- **Send reply:** `ChatThread` posts to the role-appropriate message endpoint.
  FastAPI assigns the sender, role, type, and timestamp, then commits the
  message. React clears the composer only after successful storage. A failed
  request retains the draft. Public replies on CLOSED tickets are rejected;
  an agent can reopen them. Customer replies do not change status or priority;
  those fields are controlled only by authenticated agents.
- **Internal note:** only an authenticated agent can submit `kind: INTERNAL`.
  Customer schemas reject that field. Both customer REST responses and SSE
  snapshots query PUBLIC messages only and omit the agent audit history and
  private assignment metadata. The assigned handler's name is shown to the
  customer. Database constraints also prohibit customer-authored notes.
- **Management:** the agent controls send PATCH requests. FastAPI locks the
  ticket, validates the selected agent/status/priority, and commits each change
  with its before/after audit event in the same transaction. No-op changes do
  not create extra history.
- **Drafts:** agent public/private drafts are separate and scoped to each
  ticket. They survive switching cases in the current workspace, stay in
  memory, and clear on sign-out or reload. They are not stored in the database.

React component state holds the currently displayed snapshot; PostgreSQL holds
the durable tickets, messages, events, agent accounts, and agent sessions.
Agent sign-out revokes the server-side session. Stream access is checked again
on every update cycle, rather than only at connection time.

## Live updates

`useLiveQuery` first fetches a normal authorized REST response, then opens
`EventSource` to the matching `/live` endpoint. Messages are submitted with
POST in either direction; the server sends new snapshots to both browsers.

For this small implementation, each open stream checks PostgreSQL once per
second and pushes only changed snapshots. This is server-side polling behind
SSE, not a WebSocket system. Reads release the database connection between
checks. It works across API workers because PostgreSQL is the shared source.
A heartbeat keeps quiet streams open, and reconnecting reloads the complete
current state, including messages saved while offline. The indicator means
**connection to live updates**, not agent presence or availability.

At larger scale, replace the periodic checks with PostgreSQL LISTEN/NOTIFY or
a message broker. Multiple tabs use separate HTTP streams; production hosting
must support streaming, disable proxy buffering, and use an appropriate idle
timeout. Typing indicators and read receipts remain out of scope. Staff state
uses Online/Break/Offline and a heartbeat; stale or offline handles return to
the pool. See the staff guide for the 20-second/90-second timing rules.

## API

Interactive docs: `http://127.0.0.1:8000/docs`. Browser writes must carry an
allowed Origin header. Vite forwards `/api/...` to FastAPI on port 8000.

| Method | Path | Access / behavior |
| --- | --- | --- |
| GET | `/health` | Database connectivity |
| POST | `/auth/login`, `/auth/logout` | Agent session creation/revocation |
| POST | `/auth/heartbeat` | Staff freshness without overriding an explicit Offline state |
| GET | `/help/faq` | Reviewed local FAQ revision and attribution |
| GET | `/auth/me`, `/agents` | Agent profile / assignment directory |
| GET | `/tickets` | Agent queue: status, priority, category, assigned_agent_id, unassigned, q, limit |
| POST | `/tickets` | Retired: operator creation is denied; use customer intake |
| GET / PATCH | `/tickets/{id}` | Agent conversation / audited case management |
| POST | `/tickets/{id}/messages` | Agent PUBLIC reply or INTERNAL note |
| POST | `/tickets/{id}/emergency-close` | Area team leader only; mandatory audited reason |
| GET | `/tickets/live`, `/tickets/{id}/live` | Authorized live queue / full agent conversation |
| POST | `/customer/intake/summary` | Preview local subject from category and description |
| POST | `/customer/tickets` | Answers only; generated OPEN/MEDIUM metadata, T1 routing, private access code |
| GET | `/routing`, `/routing/live` | Area-scoped staff pool and workload |
| PATCH | `/agents/me/availability` | Own accepting state and capacity |
| POST | `/customer/access` | Restore access using ticket_number and access_code |
| GET / POST | `/customer/session`, `/customer/logout` | Current customer ticket / leave ticket |
| GET | `/customer/tickets/{id}` | Only the authorized ticket's customer-visible data |
| POST | `/customer/tickets/{id}/messages` | Customer public reply; body only |
| GET | `/customer/tickets/{id}/live` | Authorized PUBLIC-only conversation snapshots |

The queue returns at most 100 recently updated matches; pagination is future
work. Customer ticket access is intentionally separate from the agent queue.
Leaving a customer ticket clears its browser cookie, while the saved private
code remains usable to return. There is no email verification or lost-code
recovery service in this demo.

## Automated checks

Start Docker PostgreSQL, Vite, and FastAPI, then run from the project root:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
npm.cmd run build
npm.cmd run lint
```

The 32 backend tests migrate a fresh `badi_test_<uuid>` PostgreSQL schema for
each test, then drop only that schema. They cover session revocation, expiry,
CSRF, input validation, ticket numbering, ownership, private-note filtering,
audit history, assignment/reassignment, filters, closed/reopened cases, and
filtered/reconnecting SSE snapshots, generated metadata, forged customer
workflow fields, T1 eligibility, FIFO/capacity/fairness, and concurrent arrivals.
Demo tables are never cleared.

For the four browser tests:

```powershell
npx.cmd playwright install chromium
npm.cmd run test:e2e
```

These use local demo credentials, create clearly labelled `[Browser test]`
tickets, and close those tickets afterwards. They exercise real customer
and agent windows, both reply directions, note isolation, failed-send draft
retention, independent public/private drafts, switching-case draft retention,
guided intake, automatic routing, assignment, status/priority changes, offline
recovery, private ticket return, logout, and mobile overflow checks. The second
test verifies the running background worker after an agent frees capacity.
The third checks inline assistant choices, typed categories, FAQ and localhost
requests. The fourth checks parking states, offline requeueing, session
restoration, supervisor restrictions, and audited emergency closure.
Screenshots stay in ignored `.local`.
The test expects the seeded demo agents and the original sample QR-code ticket.

## Remaining work and assumptions

This is a local development implementation. Production work includes request
throttling, account provisioning/password recovery, verified customer identity
or email-based recovery, HTTPS with secure cookies, monitoring, pagination,
and scaling the stream notifications. A request whose response is lost after
commit can require reconciliation before retrying; an idempotency key for
message submission is a useful next improvement. File attachments and the
optional mock order summary are not implemented.

The assignment requires a complete AI transcript/session export with the final
submission; keep this conversation for that export. The frontend and API must
be served through a same-origin production proxy when deployed (Vite's proxy
is for development only).

References: [FastAPI](https://fastapi.tiangolo.com/),
[Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events),
[Docker PostgreSQL](https://hub.docker.com/_/postgres), and
[Playwright](https://playwright.dev/docs/test-configuration).


## Administrator and attachment update

See [role architecture and enforcement](docs/roles-and-access.md) for the
Customer / Agent / Team leader / Administrator permission matrix and data flow.
Administrator sign-in is available at `http://localhost:5173/#/admin`; the local
generated login is in ignored `.local/admin-credentials.txt`. Existing agent and
leader passwords are unchanged. The Administrator workspace manages staff
profiles, role assignment, enabled state, password resets, and account deletion.

Apply migration 0006 and install the updated `backend/requirements.txt` on a
fresh checkout. `python -m app.bootstrap_admin` (with backend on PYTHONPATH)
creates the first local admin without changing an existing administrator.

Customer chat supports one PDF, PNG, JPEG, GIF, or WebP attachment per message,
up to 2 MiB. Validation happens in both React and FastAPI; PostgreSQL persists
bytes privately. Customer and staff downloads require case access. End Chat
closes the case and keeps read-only history; Start Over clears the customer
browser session and resets the chat.
The agent workspace has no new-ticket control; transfer choices expand only
after Transfer conversation is clicked.

| Method | Endpoint | Access |
| --- | --- | --- |
| GET / POST | `/admin/users` | Administrator: list / create staff |
| GET / PUT / DELETE | `/admin/users/{id}` | Administrator: read / edit profile and role / delete |
| POST | `/customer/tickets/{id}/attachments` | Authorized active customer case, multipart file + optional body |
| GET | `/customer/tickets/{id}/attachments/{attachment_id}` | Customer public case attachment |
| GET | `/tickets/{id}/attachments/{attachment_id}` | Agent / leader in the case's area |

Browser checks also cover attachment validation, live delivery, downloads,
session ending, conditional transfer controls, and Administrator CRUD on desktop
and mobile. These checks close their own verification conversations and delete
only the staff accounts they created.

The latest UI adds a compact support banner, an integrated paperclip/send
composer, image/PDF previews with explicit downloads, and persistent light/dark
mode. Capacity is Administrator-managed; agent capacity writes return 403.
The Administrator directory uses navigation, tables, search, role filters,
pagination and profile dialogs. Migration 0007 persists customer disconnection
and idempotent closure. See the [current UI guide](docs/roles-and-access.md#current-ui-and-theme).

## Message activity and security review

Customers see public agent typing and Seen receipts. Agents get red unread
counts and italic Awaiting reply timers. Only visible customer messages are
acknowledged; background/offscreen/preview-covered conversations stay unread.
Internal notes neither publish typing nor reset public reply timers. Staff
dark mode uses neutral slate/charcoal surfaces.

Migration 0008 adds read cursors, receipt times, six-second typing presence,
shared request budgets and file quarantine. Writes to `/tickets/{id}/read` and
`/tickets/{id}/typing` require the current handler. No draft text is sent.
Customer and queue SSE snapshots carry the resulting metadata automatically.

The [security review](docs/security-review-2026-11-10.md) records patches,
verification and remaining deployment limits. Uploads are sanitized in a
time-bounded process and existing files were revalidated. No antivirus service
is configured. Docker image CVE scanning requires Docker sign-in; this local
setup is not a completed production security deployment.
