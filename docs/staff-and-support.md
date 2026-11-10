# Support sessions and staff roles

## Customer and FAQ

`SupportPage.tsx` renders the assistant and conversation. `FaqPage.tsx` renders
searchable quick answers at `#/faq`, linked separately in the public navigation.
It first calls `/customer/session`: a valid HttpOnly cookie restores the case
without exposing the token to React. Completed cases restore as read-only
history. There is no separate Return to a Ticket card.

`CustomerBot.tsx` offers new help, private-code recovery, and FAQ navigation
inside the conversation. `/customer/access` accepts the private code alone
(an optional ticket number remains for backwards compatibility). Active cases
resume; completed cases offer history or a new chat. Email and readable
ticket numbers alone never unlock a case. Empathetic prompts are deterministic;
the bot does not invent waiting times or send text to an external AI provider.

Eight concise support adaptations of [Badi's published FAQ](https://badiesim.com/help/faq)
are stored in `backend/content/faq.v1.json`. The revision includes the source
page/API, review date, identifier, and a hash of upstream content. `/help/faq`
serves the reviewed local copy, so a source-site outage cannot prevent support.
React renders plain text, not untrusted remote HTML.

Check for upstream changes:

```powershell
backend/.venv/Scripts/python.exe backend/check_faq_source.py
```

A change returns a nonzero exit code and asks for review. Retain the previous
revision, create the new versioned file, then update `FAQ_PATH` after review.
The check never silently publishes external content.

## Permission matrix

The existing `agents` table now stores staff `role`, `area`, and `availability`.
Admin / Team Leader is one `TEAM_LEAD` supervisor role in this step; it is
not an unrestricted general administrator.

| Role | Read cases | Send messages | Normal edits | Emergency close |
| --- | --- | --- | --- | --- |
| Customer | Authorized case, public content | Own active case, PUBLIC only | No | No |
| AGENT | Own support area | Their assigned cases, public replies or notes | Own workflow; explicit area handoffs | No |
| TEAM_LEAD | All area cases, notes, and audit | No | No | Own area, with reason |

`security.py` defines separate staff/operator/leader dependencies. Route
handlers scope lists, details, streams, directories and closures by area.
Roles come from PostgreSQL; supplying a role during login is rejected.
The default demo area is `BADI_SUPPORT`; cross-area isolation is tested with
a second area. Area/account management screens are future work.

Both roles sign in at `#/agent`, which selects the appropriate workspace.
Public Home navigation is absent there; the account avatar shows role/state.

## Inbox and availability

Each operator's inbox shows their assigned cases. There are no shared-pool tabs
or separate agent cards. The invisible queue is the
SQL set of active unassigned cases, routed FIFO to the least-loaded eligible
T1 operator in the same area, within automatic capacity. Leaders never receive
automatic assignments.

- Online accepts new cases.
- Break pauses new assignments and retains existing handles.
- Offline returns active handles immediately, audits the removal, and routes
  them to other eligible operators or leaves them waiting in the pool.
- Last-session logout goes Offline. Historical RESOLVED/CLOSED cases retain
  their assignee; messages and case status are never erased by a transfer.

The browser calls `/auth/heartbeat` every 20 seconds. After 90 seconds without
a fresh heartbeat from any session, the two-second worker marks the operator
Offline and requeues active cases. The eight-hour login still allows read
access. Reconnecting updates freshness but does not override an explicit
Offline selection: choose Online to accept work again.

Routing/state changes share the PostgreSQL transaction lock. Deliberate manual
handoffs remain explicit overrides; offline or out-of-area targets are denied.
An operator cannot reply or edit another handler's parked case.

## Emergency protocol

The leader's queue and conversations are read-only. Reply/note composers,
normal edits, ticket creation, and operator state controls are absent and
also denied by the API. The leader can filter conversations by assignee.

`POST /tickets/{id}/emergency-close` requires TEAM_LEAD, matching area, and a
10–1000-character reason. The UI asks for explicit confirmation. One
transaction closes the case, sets its emergency flag, and audits actor, time,
before/after status and reason. It preserves messages. Normal agents cannot
reopen or add messages to an emergency-closed case. The private reason is
excluded from customer responses.

Active conversations use green/blue accents; CLOSED conversations use grey.
Private notes retain amber. Text labels accompany all color cues.

## Local demo and validation

`agent@example.com` is the consolidated Badi Support AGENT account;
`lead@example.com` is TEAM_LEAD. Setup seeding supplies the same local demo
password from ignored `.local/agent-credentials.txt`, without resetting
existing passwords. Both use BADI_SUPPORT. Mia’s sample login is retired. Explicit local reset remains
available with `python -m app.demo_accounts` from `backend`.

Use separate browser profiles/private contexts for different staff accounts;
tabs in one profile share the staff cookie.

The 36 PostgreSQL tests cover permissions, area isolation, ownership, session
restoration, stale-session recovery, offline requeueing, privacy, and audit.
Five browser tests cover customer/operator/leader flows, FAQ, statuses,
emergency closure, recovery and mobile layout. Only labelled test cases are
created/closed; unrelated data is preserved.


## Account menu, handoff, and reset

`StaffAccountMenu.tsx` contains Online/Break/Offline, capacity and sign-out in
one avatar disclosure. The agent directory refreshes through authenticated SSE,
so transfer options follow other agents' current availability.

`AgentWorkspace.tsx` posts explicit actions to FastAPI:

- `POST /tickets/{id}/transfer` takes `agent_id`. Only the current handler can
  transfer an active case to an online, signed-in operator in the same area
  with available capacity. Self-transfer and leader targets are rejected.
- `POST /tickets/{id}/return-to-queue` takes `{}`. The SQL ticket stores the
  returning agent and a five-minute exclusion deadline. The dispatcher can
  immediately allocate another agent, or wait for eligibility to change.
  Offline/relogin does not bypass the deadline. The normal PATCH endpoint
  rejects assignment changes, so it cannot bypass these actions.

Both use the shared queue transaction lock and record assignment history.
Status changes and emergency closure create timestamped INTERNAL system notes
in the same transaction. Customer responses/streams exclude those notes.
Dates and times display in the browser's local timezone, including the year.

The local development reset is explicit and destructive to conversations:

```powershell
$env:PYTHONPATH = 'backend'
backend/.venv/Scripts/python.exe -m app.reset_test_data
```

It checks the local `badi` database and expected sample account names, clears
tickets/messages/audit history, removes Mia's sessions/account, and retains
Badi Support and the leader with unchanged passwords. Ticket numbers keep
increasing. It does not change FAQ revisions or the database volume.


## Subsequent administrator update

The later [role architecture](roles-and-access.md) adds ADMIN as a distinct
staff-access role. This supersedes the earlier two-role matrix above. Staff
account CRUD, private attachments, End Chat behavior, and current endpoints
are described there. Existing area-scoped leader monitoring remains unchanged.
