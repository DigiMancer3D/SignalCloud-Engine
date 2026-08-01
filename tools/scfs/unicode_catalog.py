from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EmojiEntry:
    emoji: str
    name: str = ""
    category: str = ""


def _first_character(value: Any) -> str:
    text = str(value or "").strip()
    return text[0] if text else ""


def load_emoji_catalog(path: Path) -> list[EmojiEntry]:
    """Load forgiving plain-list or JSON emoji data.

    Accepted JSON roots are lists, dictionaries containing emoji/items/entries,
    or a dictionary mapping emoji to metadata. Unknown metadata is ignored.
    """
    path = Path(path)
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        return []
    items: list[Any]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        items = re.findall(r"\S+", text)
    else:
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            nested = next(
                (parsed[key] for key in ("emoji", "emojis", "items", "entries", "data")
                 if isinstance(parsed.get(key), list)),
                None,
            )
            if nested is not None:
                items = nested
            else:
                items = [
                    {"emoji": key, **(value if isinstance(value, dict) else {"name": value})}
                    for key, value in parsed.items()
                ]
        else:
            items = [parsed]
    output: list[EmojiEntry] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            emoji = _first_character(item)
            name = ""
            category = ""
        elif isinstance(item, dict):
            emoji = _first_character(
                next((item.get(key) for key in ("emoji", "char", "character", "unicode", "value", "symbol")
                      if item.get(key)), "")
            )
            name = str(item.get("name", item.get("title", item.get("label", ""))) or "")
            category = str(item.get("category", item.get("group", item.get("type", ""))) or "")
        else:
            emoji = _first_character(item)
            name = category = ""
        if emoji and emoji not in seen:
            seen.add(emoji)
            if not name:
                try:
                    name = unicodedata.name(emoji).title()
                except ValueError:
                    name = f"U+{ord(emoji):04X}"
            output.append(EmojiEntry(emoji, name, category))
    return output


def load_custom_unicode(path: Path) -> list[int]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    source = value.get("codepoints", []) if isinstance(value, dict) else value
    output: list[int] = []
    if isinstance(source, list):
        for item in source:
            try:
                code = int(str(item).removeprefix("U+"), 16) if str(item).upper().startswith("U+") else int(item)
                if 0 <= code <= 0x10FFFF and code not in output:
                    output.append(code)
            except (TypeError, ValueError):
                continue
    return output


def save_custom_unicode(path: Path, codepoints: list[int]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"schema": "scfs_custom_unicode_v1", "codepoints": sorted(set(codepoints))}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
