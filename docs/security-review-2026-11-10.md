# Security review — 10 November 2026

Scope: this Badi project’s application source, frontend routes/components/hooks,
database models and migrations, development helpers, Docker configuration,
dependency manifests, tests, and handling of existing attachments. Generated
builds and third-party source were not manually reviewed line by line; installed
dependencies were checked against vulnerability advisories. This is a local
application review, not an independent penetration test or a security guarantee.

## Findings and changes

| Finding | Change |
| --- | --- |
| Upload checks trusted parseability but preserved original payloads/metadata | Images are fully decoded and rewritten without metadata/trailing data. PDFs are rewritten after rejecting active features. Existing files were revalidated. |
| Parsing could monopolize the API or hold a ticket lock during upload | Disposable parser process, eight-second timeout, two concurrent validators per API process, 16 MP image limit, PDF limits of 100 pages / 20,000 traversed objects / depth 50. Ticket locks are acquired only after validation. |
| Login, recovery and intake lacked request budgets | PostgreSQL-backed budgets survive restarts and work across workers; failed accounts are temporarily throttled. Concurrent password verification is bounded to four. |
| Account changes could race an in-progress password check | Sign-in revalidates the account and verified hash under the account-change lock before creating a session. |
| Unbounded client activity / connection resources | Message, upload, download and presence budgets; 64 KB ordinary request limit; multipart body cap plus exact 2 MiB file cap; eight SSE streams per session and 100 per process, with expiring leases. |
| Old agent ticket-creation endpoint remained callable after its button was removed | Authenticated operator requests to that endpoint now receive 403. Requests originate through the customer intake contract. |
| Missing browser response protections and explicit private-source restrictions | API/Vite security headers, trusted hosts, production CSP with hashed inline theme initialization, explicit development file denials for backend, environment, Git and local credential files. |
| Proxy headers could distort apparent client IP | Vite strips caller-supplied forwarding headers; the local API runs with proxy-header trust disabled. |
| Legacy installer fetched executable binaries without verified integrity | Fresh legacy downloads disabled; Docker remains the supported setup. The existing PostgreSQL image is pinned by digest. Local helpers now enforce development-only targets and pin child migration/seed commands to the intended local DB. |
| Vulnerable installed Python package installer | pip upgraded from 25.2 to 26.3. Follow-up Python dependency audit reports no known vulnerabilities. |
| Staff could be named like system activity | Reserved System update name rejected for new/edited staff profiles. |

## File handling

Only PDF, PNG, JPEG, GIF and WebP are accepted. The filename extension, declared
MIME, and detected content must agree. Empty, oversized, unsupported, corrupted,
encrypted or overly complex files are rejected. Filenames are normalized and
path components, control characters, alternate-stream names and ambiguous extra
extensions cannot become filesystem paths. Files are kept as private DB bytes;
the parser writes no uploaded file to disk.

Each conversation accepts at most ten attachments (20 MiB total maximum).
The limit is rechecked under the ticket lock, preventing concurrent uploads
from racing past the storage budget.

PNG/JPEG/WebP are re-encoded without EXIF/text metadata. GIF is reduced to a
sanitized PNG frame. Rewritten output must still fit within 2 MiB. PDF JavaScript,
launch actions, open/additional actions, external links, forms, embedded files and
related active content are rejected; upload a flattened PDF instead. Parser
failure/timeouts reject the upload rather than saving an unchecked original.

The Windows worker bypasses the venv launcher and executes the real interpreter
directly, so timeout termination cannot leave a redirected parser child running.
It uses isolated Python mode and a fixed package path; customer input travels
only over stdin, never as shell commands or Python code.

Eleven pre-existing attachments were revalidated and rewritten; none required
quarantine. A rejected stored file is retained but blocked from downloads and
previews. Recheck locally with:

```powershell
$env:PYTHONPATH = 'backend'
backend/.venv/Scripts/python.exe -m app.rescan_attachments
# Review the report, then add --apply to persist sanitization/quarantine.
```

Downloads check customer ownership or staff area, attachment membership and
quarantine state. Customer downloads additionally require a PUBLIC message.
They are served as attachments with nosniff and no-store. Preview bytes come
through the same authorized endpoint. PDF.js receives byte arrays directly;
PDF scripts/annotations are not mounted and no third-party viewer receives files.

This follows the layered approach in the [OWASP upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

## Authentication, roles and response boundaries

Opaque session tokens are hashed in SQL and carried in HttpOnly, SameSite=Strict
cookies. Successful sign-in replaces the previous cookie session for that same
account. Authorization checks the current active account and role; access changes
revoke sessions. Customers cannot set workflow metadata, send internal notes,
acknowledge messages as an agent, or publish typing presence. Leaders/admins
cannot impersonate an operator through presence endpoints.

Read cursors are monotonic and scoped to an agent and ticket. A receipt must
reference a public customer message in the current handler’s ticket. A customer
cannot inject another agent identity. Typing presence expires after six seconds,
is restricted to active assigned cases, and does not reveal private drafts.

SQLAlchemy binds user values; queue searches escape wildcard input. React renders
message text as text, not HTML. No authorization token is kept in localStorage;
only the theme preference is stored there. No local environment/credential files
are tracked in Git, and HTTP tests verify that Vite does not serve them.

Write requests require an exact allowed Origin. Login failures use generic
messages and durable throttling, consistent with [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
Limits are: 100 sign-in attempts per peer/minute, ten failed attempts per account
per ten minutes, 30 recoveries per peer/five minutes, and 15 new cases per peer/ten
minutes in production (60 locally). They are abuse controls, not a DDoS defense.

Production settings refuse insecure cookies, HTTP/wildcard origins and wildcard
or test hosts. API docs are disabled in production. HSTS is set in production;
TLS termination and proxy trust must be configured by the deployment owner.
Development CSP permits Vite’s inline refresh bootstrap; production uses exact
script hashes. Inline style declarations remain allowed for UI/PDF dimensions.

## Verification and remaining limits

- Build/lint passed; 58 PostgreSQL integration tests and nine browser tests passed.
- npm audit: zero reported vulnerabilities in the current lockfile.
- pip-audit: zero known vulnerable installed packages after the pip update.
- Bandit: no medium/high findings; nine low subprocess/import warnings were
  reviewed as fixed argument-vector developer commands / parser isolation. No
  untrusted input is passed through a shell. Raw reports are in ignored
  `.local/security/`.
- Real PostgreSQL regression tests include role/area boundaries, private-note
  isolation, forged receipt IDs, typing expiry, headers/hosts/origins, request
  limits, active PDF rejection, image sanitization, quarantine and session rotation.
- Browser tests exercise real typing/Seen/unread transitions, public-only timer
  reset, private file denial, existing chat/admin flows, previews and downloads.
- The built production bundle’s CSP hashes and application startup were verified
  in Chromium; local development and production policies are distinct.

Outstanding boundaries:

1. No upload antivirus service is configured; Windows Defender reported disabled
   on this machine. Sanitization/validation does not certify files malware-free.
   Before public deployment, add a maintained malware scanner/CDR service and
   stronger OS/container memory/sandbox limits for parsing. The parser process is
   fault isolation, not an OS security sandbox.
2. Docker Scout could not scan the PostgreSQL image’s OS packages because Docker
   is not signed in. Pinning the image does not prove the absence of image CVEs.
3. This remains a local development deployment. Production also needs HTTPS,
   explicit trusted-proxy/client-IP handling, separate migration/runtime DB roles,
   secret management, backups, monitoring and a public-edge connection/rate limit.
   Per-process stream/parser budgets do not replace those controls. MFA is not
   implemented. Local sample credentials must not be reused for public staff access.
