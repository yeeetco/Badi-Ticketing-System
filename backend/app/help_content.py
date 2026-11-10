import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()
FAQ_PATH = Path(__file__).resolve().parents[1] / 'content' / 'faq.v1.json'


@router.get('/help/faq')
def faq():
    # Serve the reviewed revision locally; an external-site failure must not
    # prevent someone from opening a support conversation.
    return json.loads(FAQ_PATH.read_text(encoding='utf-8'))
