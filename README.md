# Badi eSIM support ticketing

React + TypeScript + Vite frontend, with a FastAPI and PostgreSQL backend.

This learning step adds private agent sign-in and a database-backed ticket queue. The customer support page is still a placeholder. Chat, filters, assignment, status edits, internal notes, audit history, and real-time updates are upcoming steps, not completed features.

## Page map

- Customer: `#/` -> `#/support` -> later: new/existing request -> ticket conversation.
- Agent: open `#/agent` directly -> sign in -> queue -> later: conversation and management controls.

The public navigation has no agent link. The URL itself is not a security boundary: FastAPI checks a valid agent session before returning ticket data. There is no separate admin role.

## Windows setup

Run these commands in PowerShell from the project root. Python 3.13+ is required.

```powershell
npm install
py -3.13 -m venv backend/.venv
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

Start the database again after a reboot:

```powershell
backend/.venv/Scripts/python.exe backend/dev_database.py start
```

In one terminal, run the API:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

In another terminal, run the frontend:

```powershell
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Visit `http://127.0.0.1:5173/` for the homepage. Open `http://127.0.0.1:5173/#/agent` directly for agent sign-in. Use the credentials in `.local/agent-credentials.txt`. Refreshing preserves the eight-hour session; signing out revokes it immediately on the server.

The Vite configuration changed to add the API proxy. Restart Vite if an older instance is still running. Use port 5173: writes from other origins are deliberately rejected unless you add that exact origin to `ALLOWED_ORIGINS` in `backend/.env` and restart FastAPI.

Stop the foreground servers with Ctrl+C. Stop the database with:

```powershell
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

## Follow the code

| File | Responsibility |
| --- | --- |
| `src/App.tsx` | Hash route map and public navigation |
| `src/pages/HomePage.tsx` | Homepage and Contact Support link |
| `src/pages/AgentPage.tsx` | Session check, sign-in form, and queue loading/empty/error states |
| `src/api.ts` | All frontend HTTP requests to `/api` |
| `vite.config.ts` | Development proxy from `/api` to FastAPI on port 8000 |
| `backend/app/main.py` | HTTP endpoints, validation responses, and write-origin checks |
| `backend/app/security.py` | Password hashing and server-side session authorization |
| `backend/app/models.py` | SQLAlchemy tables for agents, sessions, and tickets |
| `backend/migrations/versions/0001_agent_access.py` | Versioned PostgreSQL schema |
| `backend/app/seed.py` | Repeatable demo data |
| `backend/tests/test_agent_access.py` | PostgreSQL integration tests |

The code uses blank lines and comments around the important boundaries so you can add your own notes.

### What happens on sign-in

1. React sends the email and password to `/api/auth/login`.
2. Vite forwards that to FastAPI `/auth/login`.
3. FastAPI verifies the Argon2 password hash in PostgreSQL and creates a random eight-hour session.
4. The browser gets an HttpOnly, SameSite=Strict cookie. JavaScript never reads the token; the database stores only its SHA-256 digest.
5. React requests `/api/tickets`. FastAPI validates the session before querying tickets.
6. React stores the returned rows in component state and renders the table. PostgreSQL remains the persistent source of truth.

Changing React state or entering the URL cannot authorize an API request. Logout deletes the session from PostgreSQL. Cross-origin writes are rejected using the request Origin header, including sign-in. Non-browser clients must also send an allowed Origin header.

## API available in this step

FastAPI interactive docs: `http://127.0.0.1:8000/docs`.

| Method | Path | Access |
| --- | --- | --- |
| GET | `/health` | Checks database connectivity |
| POST | `/auth/login` | Valid agent email and password; allowed Origin |
| GET | `/auth/me` | Signed-in agent |
| POST | `/auth/logout` | Revokes current session; allowed Origin |
| GET | `/tickets` | Signed-in agent; most recent 50 rows by default, up to 100 with `limit` |
| POST | `/tickets` | Signed-in agent; allowed Origin |

To create a ticket through `/docs`, first sign in through its `/auth/login` endpoint on that same host. Then use `/tickets` with:

```json
{
  "customer_email": "customer@example.com",
  "order_id": "ORD-10293",
  "category": "CONNECTIVITY",
  "subject": "eSIM installed but no internet",
  "description": "The eSIM is installed, but mobile data does not work.",
  "priority": "HIGH"
}
```

New tickets get a PostgreSQL-generated number such as `BD-1004` and start in `OPEN`. Concurrent inserts use a database identity, never row counting. Sequence gaps after rolled-back transactions are expected. Refresh the agent page to see a newly created ticket in this step; real-time conversation updates come later.

Customer creation and ticket access will have separate ownership checks. Do not make the agent queue public to support the customer flow. Internal notes will require separate agent-only authorization and customer response filtering when the messaging endpoints are implemented.

## Verification

With PostgreSQL running and `backend/.env` configured:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
npm run build
npm run lint
```

The tests run the real migration inside a fresh `badi_test_<uuid>` PostgreSQL schema for each test, then drop only that schema. They never clear the demo tables. Tests cover unauthorized access, incorrect passwords, cookie settings, logout revocation, session expiry, CSRF protection, ticket numbering, OPEN status, and input validation.

Manual test:

1. Check that Home has only Home and Contact Support in the public navigation.
2. Open `#/agent` in a private window: only the sign-in form should appear.
3. Try an incorrect password, then use the generated demo credentials.
4. Confirm the three demo tickets appear. Refresh and confirm you remain signed in.
5. Sign out and confirm the queue disappears; refresh and confirm sign-in is required.

For a small edit, change the sign-in introduction in `src/pages/AgentPage.tsx`; Vite will update it immediately.

## Scope and later work

This is a local development slice, not the completed interview submission. There is no customer authentication, chat, ticket-detail endpoint, PATCH endpoint, filtering, audit trail, or real-time transport yet. Later steps will add each with tests. Before deployment, add login throttling, account provisioning/password recovery, HTTPS with secure cookies, and a same-origin production reverse proxy (Vite's proxy is development-only).

The assignment requires a complete AI transcript/session export with the eventual submission. Keep this conversation for that export. Upcoming backend tests should include status-change audit events and customer/internal-note separation once those features exist.

References used for implementation: [FastAPI password hashing](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/), [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/tutorial.html), and [PostgreSQL Windows distributions](https://www.postgresql.org/download/windows/).
