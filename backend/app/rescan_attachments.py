"""Revalidate stored local attachments, preserving rejected bytes in quarantine."""
import argparse
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import engine
from .file_validation import validate_isolated
from .models import Attachment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Persist sanitized files; block rejected originals.')
    apply = parser.parse_args().apply
    if settings.environment != 'development' or engine.url.host not in ('localhost', '127.0.0.1') or engine.url.database != 'badi':
        raise SystemExit('This helper is restricted to the local badi development database.')
    results = []
    with Session(engine) as db:
        ids = list(db.scalars(select(Attachment.id)).all())
        db.rollback()
        for attachment_id in ids:
            attachment = db.get(Attachment, attachment_id)
            if not attachment:
                continue
            try:
                name, mime, canonical = validate_isolated(attachment.filename, attachment.content_type, attachment.payload)
                if apply:
                    attachment.filename, attachment.content_type = name, mime
                    attachment.payload, attachment.size, attachment.blocked = canonical, len(canonical), False
                result = 'sanitized'
            except Exception:
                if apply:
                    attachment.blocked = True  # Retain original bytes for review, never distribute them.
                result = 'quarantined'
            if apply:
                db.commit()
            else:
                db.rollback()
            results.append({'attachment_id': attachment_id, 'result': result})
    path = Path(__file__).resolve().parents[2] / '.local/security/attachment-rescan.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'applied': apply, 'results': results}, indent=2), encoding='utf-8')
    print(f"Checked {len(results)} stored attachments; {sum(row['result'] == 'quarantined' for row in results)} quarantined; applied={apply}.")


if __name__ == '__main__':
    main()
