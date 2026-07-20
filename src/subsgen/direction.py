from __future__ import annotations

import unicodedata


def is_rtl_text(text: str) -> bool:
    """Return the dominant direction of strong Unicode characters in text."""
    rtl = 0
    ltr = 0
    first: bool | None = None
    for character in text:
        direction = unicodedata.bidirectional(character)
        if direction in {"R", "AL"}:
            rtl += 1
            if first is None:
                first = True
        elif direction == "L":
            ltr += 1
            if first is None:
                first = False
    if rtl == ltr:
        return bool(first)
    return rtl > ltr
