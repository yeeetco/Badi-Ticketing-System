"""Small durable request budgets shared by API workers; keys contain no PII."""
from datetime import datetime, timedelta, timezone
import hashlib
import math

from fastapi import HTTPException
from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert

from .models import RateLimitBucket


def key_for(scope, subject):
    return hashlib.sha256(f'{scope}:{subject}'.encode()).hexdigest()


def client_key(request):
    # Do not trust caller-supplied X-Forwarded-For. A production proxy needs
    # explicit trusted-proxy configuration; direct/local requests use peer IP.
    return request.client.host if request.client else 'unknown'


def consume(db, scope, subject, limit, seconds):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=seconds)
    key = key_for(scope, subject)
    old = RateLimitBucket
    expired = old.expires_at <= now
    statement = insert(old).values(key=key, count=1, expires_at=expires).on_conflict_do_update(
        index_elements=['key'], set_={'count': case((expired, 1), else_=old.count + 1),
                                      'expires_at': case((expired, expires), else_=old.expires_at)},
    ).returning(old.count, old.expires_at)
    count, deadline = db.execute(statement).one()
    db.execute(delete(old).where(old.expires_at < now - timedelta(hours=1)))
    # Called before application writes/locks. Rejected requests cannot roll back
    # their own budget, and a worker restart does not reset the protection.
    db.commit()
    if count > limit:
        raise HTTPException(429, 'Too many requests. Please try again shortly.', headers={
            'Retry-After': str(max(1, math.ceil((deadline - now).total_seconds())))})


def check_login_failures(db, email):
    bucket = db.get(RateLimitBucket, key_for('login-failure', email.lower()))
    if bucket and bucket.expires_at > datetime.now(timezone.utc) and bucket.count >= 10:
        raise HTTPException(429, 'Too many sign-in attempts. Please try again later.', headers={'Retry-After': '600'})


def clear_login_failures(db, email):
    db.execute(delete(RateLimitBucket).where(RateLimitBucket.key == key_for('login-failure', email.lower())))
