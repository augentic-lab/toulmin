"""Terminal-width output for text views (UX2).

Only an interactive terminal is wrapped: piped or redirected output, tests and agents reading
command output keep exact, unwrapped lines.
"""

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
