"""Short labels for object text in terminal views (UX2).

Pure text shaping: an ID alone says nothing, so views put a short label beside it. A label is
the whole text when it fits, else its first sentence when that fits, else the text cut at a
word boundary. Width counts East Asian wide characters as two columns. Nothing here reads or
writes files.
"""

import re
import unicodedata

SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|(?<=[。！？；])")
TRAILING = " ,;:-–—(["


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def _cut(text: str, width: int) -> str:
    """The longest prefix within ``width`` columns."""
    kept, used = [], 0
    for char in text:
        size = display_width(char)
        if used + size > width:
            break
        kept.append(char)
        used += size
    return "".join(kept)


def short_label(text: str, width: int, ellipsis: str = "…") -> str:
    """``text`` shortened to ``width`` columns without splitting a word."""
    # Summaries are already one line and may end with a "..." marking an earlier cut.
    flat = " ".join(text.split())
    cut_before = flat.endswith("...")
    flat = flat.removesuffix("...").rstrip()
    if width <= display_width(ellipsis):
        return _cut(flat, width)
    if not cut_before and display_width(flat) <= width:
        return flat
    first = SENTENCE_END.split(flat, maxsplit=1)[0].rstrip()
    if first != flat and display_width(first) <= width:
        return first
    room = width - display_width(ellipsis)
    kept = _cut(flat, room)
    if len(kept) < len(flat) and not flat[len(kept)].isspace():
        # Mid-word: go back to the last space unless that loses most of the room.
        space = kept.rfind(" ")
        if space >= len(kept) // 2:
            kept = kept[:space]
    return kept.rstrip(TRAILING) + ellipsis
