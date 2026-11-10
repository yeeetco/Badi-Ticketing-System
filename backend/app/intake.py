"""Local extractive summaries: no API key, remote model, or invented facts."""
import re


def summarize_issue(description: str, category: str) -> str:
    text = re.sub(r'\s+', ' ', description).strip()
    # Remove an introductory greeting, then keep the first substantive sentence.
    text = re.sub(r'^(?:hi|hello|hey)(?:\s+(?:there|team|support))?[,!:;\s]+', '', text, flags=re.I)
    sentence = re.split(r'(?<=[.!?])\s+', text, maxsplit=1)[0].strip()
    if not sentence:
        sentence = f'{category.replace("_", " ").capitalize()} support request'
    if len(sentence) > 100:
        sentence = sentence[:97].rsplit(' ', 1)[0].rstrip('.,;:') + '…'
    return sentence[0].upper() + sentence[1:]
