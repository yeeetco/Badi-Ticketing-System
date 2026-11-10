"""Check for upstream FAQ changes without silently publishing unreviewed text."""
import hashlib
import json
from pathlib import Path

import httpx

path = Path(__file__).parent / 'content' / 'faq.v1.json'
revision = json.loads(path.read_text(encoding='utf-8'))
response = httpx.get(revision['source_api'], timeout=30, follow_redirects=True)
response.raise_for_status()
content_hash = hashlib.sha256(json.dumps(response.json()['content'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
changed = content_hash != revision['source_content_sha256']
print('FAQ source changed; review and create a new content revision.' if changed else 'FAQ source matches the reviewed revision.')
raise SystemExit(1 if changed else 0)
