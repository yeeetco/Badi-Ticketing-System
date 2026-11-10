"""Per-process SSE connection budgets with expiring leases for abandoned streams."""
import secrets
import threading
import time

from fastapi import HTTPException

leases = {}
guard = threading.Lock()


def acquire(principal):
    now = time.monotonic()
    with guard:
        for lease, (_, expiry) in list(leases.items()):
            if expiry <= now:
                leases.pop(lease, None)
        if len(leases) >= 100 or sum(owner == principal for owner, _ in leases.values()) >= 8:
            raise HTTPException(429, 'Too many live connections. Close unused support tabs and retry.', headers={'Retry-After': '10'})
        lease = secrets.token_hex(16)
        leases[lease] = (principal, now + 90)
        return lease


def touch(lease):
    with guard:
        if lease in leases:
            leases[lease] = (leases[lease][0], time.monotonic() + 90)


def release(lease):
    with guard:
        leases.pop(lease, None)
