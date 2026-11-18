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
