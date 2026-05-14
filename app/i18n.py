import json
import os
from pathlib import Path
from functools import lru_cache

LOCALES_DIR = Path(__file__).parent.parent / "locales"


@lru_cache(maxsize=8)
def _load_locale(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def t(key: str, lang: str = "de", **kwargs: str) -> str:
    translations = _load_locale(lang)
    text = translations.get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text
