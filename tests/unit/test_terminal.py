"""UX2: terminal-width wrapping only in an interactive terminal."""

import typer

from toulmin.cli import terminal


def test_wrapping_keeps_words_names_and_indents():
    line = "  C-002 | stored=proposed | verified_support=1 | open_objection=yes | rkey-lifecycle"
    parts = terminal.wrapped(line, 50)
    assert parts[0].startswith("  C-002") and all(part.startswith("      ") for part in parts[1:])
    assert " ".join(part.strip() for part in parts) == line.strip()
    assert any("rkey-lifecycle" in part for part in parts)  # never split at the hyphen
    long_path = "Last handoff: projects/demo/sessions/" + "a" * 80 + ".md"
    assert terminal.wrapped(long_path, 40)[-1].endswith(".md")  # a path is kept whole
    assert terminal.wrapped("short", 40) == ["short"]


def test_piped_output_is_not_wrapped(monkeypatch):
    monkeypatch.setattr(terminal, "interactive", lambda: False)
    assert terminal.sayer() is typer.echo


def test_terminal_output_is_wrapped(monkeypatch, capsys):
    monkeypatch.setattr(terminal, "interactive", lambda: True)
    monkeypatch.setenv("COLUMNS", "40")
    terminal.sayer()("word " * 20)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) > 1 and all(len(line) <= 40 for line in lines)


def test_colour_only_on_a_terminal_and_never_with_no_color(monkeypatch):
    card = "\n".join(
        [
            "demo · critique",
            "─" * 40,
            "Answer    ✓ C-005 Keys are not rejected.  (ready to rule supported)",
            "          ? C-002 Collisions.  (1 fatal, 4 major open)",
            "Doubts    C-002 5 major, 1 minor: O-007 Only a condition.",
        ]
    )
    monkeypatch.setattr(terminal, "interactive", lambda: False)
    assert terminal.colour(card) == card
    monkeypatch.setattr(terminal, "interactive", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    coloured = terminal.colour(card)
    assert "\x1b[2m" + "─" * 40 in coloured  # rules dimmed
    assert "\x1b[32m✓\x1b[0m C-005" in coloured and "\x1b[33m?\x1b[0m C-002" in coloured
    assert "\x1b[1mAnswer\x1b[0m" in coloured and "\x1b[1m\x1b[31mfatal\x1b[0m" in coloured
    assert "C-005" in coloured and coloured.count("\n") == card.count("\n")
    monkeypatch.setenv("NO_COLOR", "1")
    assert terminal.colour(card) == card
