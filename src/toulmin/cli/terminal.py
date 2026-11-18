"""Terminal-width output for text views (UX2).

Only an interactive terminal is wrapped: piped or redirected output, tests and agents reading
command output keep exact, unwrapped lines.
"""

import os
import re
import shutil
import sys
import textwrap
from collections.abc import Callable

import typer


def interactive() -> bool:
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def wrapped(line: str, width: int) -> list[str]:
    """One output line wrapped at word boundaries; continuation lines indent past its own."""
    if len(line) <= width or not line.strip():
        return [line]
    indent = " " * (len(line) - len(line.lstrip(" ")) + 4)
    return textwrap.wrap(
        line,
        width,
        subsequent_indent=indent,
        break_on_hyphens=False,
        break_long_words=False,
        drop_whitespace=True,
    ) or [line]


def sayer() -> Callable[..., None]:
    """``typer.echo`` that wraps each line to the terminal width when attached to one."""
    if not interactive():
        return typer.echo
    width = max(shutil.get_terminal_size((80, 24)).columns, 40)

    def say(message: str = "", nl: bool = True) -> None:
        lines = message.split("\n")
        text = "\n".join(part for line in lines for part in wrapped(line, width))
        typer.echo(text, nl=nl)

    return say


# UX5: colour after layout, so widths never count escape codes; terminals only, NO_COLOR wins.
CODES = {"bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33"}
RULE = re.compile(r"^[─-]{20,}$")
TITLE = re.compile(r"^([A-Z][A-Za-z]+)( +)")
MARK = re.compile(r"^( {10}|[A-Z][A-Za-z]+ +)([✓?✗!·+x.]) (?=[A-Z]-[0-9])")
SEVERITY = re.compile(r"\b(fatal|major|minor|OPEN|WARNING|INVALID)\b")
MARK_COLOUR = {"✓": "green", "+": "green", "?": "yellow", "✗": "red", "x": "red", "!": "red"}
WORD_COLOUR = {
    "fatal": ("bold", "red"),
    "major": ("yellow",),
    "minor": ("dim",),
    "OPEN": ("yellow",),
    "WARNING": ("bold", "red"),
    "INVALID": ("bold", "red"),
}


def colour_enabled() -> bool:
    return interactive() and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"


def paint(text: str, *styles: str) -> str:
    return "".join(f"\x1b[{CODES[style]}m" for style in styles) + text + "\x1b[0m"


def colour(text: str) -> str:
    """Card and map text with titles, marks and severities coloured; unchanged off a terminal."""
    if not colour_enabled():
        return text
    lines = []
    for line in text.split("\n"):
        if RULE.match(line):
            lines.append(paint(line, "dim"))
            continue
        mark = MARK.match(line)
        if mark and mark.group(2) in MARK_COLOUR:
            start, end = mark.span(2)
            line = line[:start] + paint(line[start:end], MARK_COLOUR[mark.group(2)]) + line[end:]
        title = TITLE.match(line)
        if title and len(title.group(0)) == 10:  # the card's left column
            line = paint(title.group(1), "bold") + line[len(title.group(1)) :]
        line = SEVERITY.sub(lambda match: paint(match.group(1), *WORD_COLOUR[match.group(1)]), line)
        lines.append(line)
    return "\n".join(lines)
