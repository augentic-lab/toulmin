"""L3: render the research map (V2) and redraw it when files change.

Read-only: nothing is written, locked or cached. ``--watch`` polls file metadata and
recomputes the map only when that metadata changes.
"""

import os
import shutil
import sys
import textwrap
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path

from toulmin.cli import decide
from toulmin.cli.initialize import workspace_setup
from toulmin.core.identifiers import ObjectId
from toulmin.core.project import STAGES
from toulmin.protocols.research_map import AGENT, YOU, Node, ResearchMap, research_map
from toulmin.protocols.status import GateReadiness
from toulmin.protocols.workspace_state import RootState, workspace_status

CLEAR = "\x1b[H\x1b[2J"
NEXT_GATE = {"explore": "G1", "critique": "G2"}
WAITING_SHOWN = 8


class Glyphs:
    def __init__(self, ascii_only: bool) -> None:
        self.done, self.here, self.ahead = ("x", "*", "o") if ascii_only else ("✓", "●", "○")
        self.line = "-" if ascii_only else "─"
        self.branch, self.last, self.down = (
            ("|- ", "`- ", "|  ") if ascii_only else ("├─ ", "└─ ", "│  ")
        )
        self.dot = "|" if ascii_only else "·"
        self.step = ">" if ascii_only else "›"
        self.ascii = ascii_only


def ascii_default() -> bool:
    encoding = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    return encoding != "utf8"


def width_of(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def fit(text: str, width: int) -> str:
    """Cut a line to the display width, marking the cut."""
    if width_of(text) <= width:
        return text
    kept, used = [], 0
    for char in text:
        size = width_of(char)
        if used + size > width - 3:
            break
        kept.append(char)
        used += size
    return "".join(kept) + "..."


def wrap(text: str, width: int, indent: str) -> list[str]:
    return textwrap.wrap(text, max(width, 20), subsequent_indent=indent) or [""]


def track(stage: str | None, width: int, glyphs: Glyphs) -> str:
    if stage not in STAGES:
        return f"Stage: {stage or 'unknown'}"
    here = STAGES.index(stage)
    parts = []
    for index, name in enumerate(STAGES):
        mark = glyphs.done if index < here else glyphs.here if index == here else glyphs.ahead
        parts.append(f"{mark} {name}")
    line = parts[0]
    for index, part in enumerate(parts[1:], start=1):
        line += f" {glyphs.line}G{index}{glyphs.line} {part}"
    plain = f" {glyphs.step} ".join(parts)  # gate names are in the gate lines below
    for candidate in (line, plain):
        if width_of(candidate) <= width:
            return candidate
    after = f"; next {STAGES[here + 1]} via G{here + 1}" if here + 1 < len(STAGES) else ""
    return f"Stage {here + 1}/{len(STAGES)}: {stage}{after}"


def _count(gate: GateReadiness) -> str:
    if gate.met is None:
        return "unknown (data invalid)"
    met = sum(item.met for item in gate.items)
    return f"{met}/{len(gate.items)}" + (" met" if gate.met else "")


def _node_line(node: Node, glyphs: Glyphs) -> str:
    if node.object_id == "plan":
        return f"plan: {node.summary}"
    facts = [
        ("← " + fact[3:]) if fact.startswith("<- ") and not glyphs.ascii else fact
        for fact in node.facts
    ]
    head = f"{node.object_id} " + f" {glyphs.dot} ".join(facts)
    return f"{head}  {node.summary}" if node.summary else head


def _branch(nodes: tuple[Node, ...], prefix: str, width: int, glyphs: Glyphs) -> list[str]:
    lines = []
    for index, node in enumerate(nodes):
        last = index == len(nodes) - 1
        mark = glyphs.last if last else glyphs.branch
        lines.append(fit(prefix + mark + _node_line(node, glyphs), width))
        lines += _branch(node.children, prefix + ("   " if last else glyphs.down), width, glyphs)
    return lines


def render_project(
    report: ResearchMap,
    waiting: list[decide.Item],
    width: int,
    glyphs: Glyphs,
    refreshed: str | None = None,
    claim: str | None = None,
) -> str:
    head = report.project + ("  (data INVALID: partial view)" if report.errors else "")
    if refreshed:
        pad = width - width_of(head) - width_of(f"refreshed {refreshed}")
        head += " " * max(pad, 2) + f"refreshed {refreshed}"
    lines = [head, track(report.stage, width, glyphs), ""]

    following = NEXT_GATE.get(report.stage or "")
    for gate in report.gates:
        title = f"{gate.gate} -> {gate.enters}  {_count(gate)}"
        if gate.gate != following:
            lines.append(fit(title, width))
            continue
        lines.append(fit(title + "  (advice; the stage changes only by your ruling)", width))
        for item in gate.items:
            detail = f": {item.detail}" if item.detail else ""
            lines.append(fit(f"  [{'x' if item.met else ' '}] {item.label}{detail}", width))
    lines.append("")

    lines.append(f"Waiting on you (toulmin decide): {len(waiting) or 'nothing'}")
    for entry in waiting[:WAITING_SHOWN]:
        label = decide.LABEL.get(entry.kind, entry.kind)
        interrupted = any(
            pending.path == entry.path and pending.interrupted for pending in report.pending
        )
        name = entry.path.rsplit("/", 1)[-1]
        note = " (interrupted application)" if interrupted else ""
        lines.append(fit(f"  {label}: {name}{note}", width))
    if len(waiting) > WAITING_SHOWN:
        lines.append(f"  ... {len(waiting) - WAITING_SHOWN} more")
    for run, labels in report.undecided:
        lines.append(fit(f"Review drafts without intake: {run}: {', '.join(labels)}", width))
    lines.append("")

    lines.append("Suggested next (advice; you rule)")
    for number, move in enumerate(report.moves, start=1):
        who = {YOU: "you", AGENT: "agent"}.get(move.actor, "either")
        first = f"  {number} {who:<6} "
        lines += wrap(first + move.text, width, " " * len(first))
    lines.append("")

    claims = report.claims
    if claim is not None:
        claims = tuple(node for node in claims if node.object_id == claim)
        if not claims:
            lines.append(f"{claim} is not a current Claim of {report.project}.")
    if not report.claims:
        lines.append("Argument: no Claims yet.")
    elif claims:
        lines.append("Argument")
    for node in claims:
        lines.append(fit(_node_line(node, glyphs), width))
        lines += _branch(node.children, "", width, glyphs)
    if report.superseded and claim is None:
        arrow = " -> " if glyphs.ascii else " → "
        lines.append(
            fit("Superseded: " + ", ".join(arrow.join(c) for c in report.superseded), width)
        )
    if report.decisions and claim is None:
        lines.append("Decisions")
        lines += [fit("  " + _node_line(node, glyphs), width) for node in report.decisions]
    if report.elsewhere and claim is None:
        lines.append(fit("Aimed elsewhere: " + ", ".join(report.elsewhere), width))
    if report.errors:
        lines += ["", "Errors"]
        for message in report.errors:
            lines += wrap(f"  {message}", width, "    ")
    return "\n".join(lines) + "\n"


def render_workspace(root: Path, width: int, glyphs: Glyphs, refreshed: str | None = None) -> str:
    report = workspace_status(root, workspace_setup())
    if report.root.state not in {RootState.WORKSPACE, RootState.LEGACY}:
        raise ValueError(f"{report.root.root}: not a Toulmin workbench")
    base = report.root.root
    head = f"Workspace {base.name}"
    if refreshed:
        head += f"  refreshed {refreshed}"
    lines = [head, ""]
    try:
        waiting = list(decide.inventory(base).items)
    except (OSError, ValueError) as error:
        waiting = []
        lines.append(fit(f"Pending decisions unknown: {error}", width))
    own = [item for item in waiting if item.project is None]
    lines.append(f"Waiting on you at the workspace (toulmin decide): {len(own) or 'nothing'}")
    for item in own[:WAITING_SHOWN]:
        lines.append(fit(f"  {decide.LABEL.get(item.kind, item.kind)}: {item.path}", width))
    lines += ["", "Projects" if report.children else "Projects: none yet"]
    for child in report.children:
        if child.error is not None:
            lines.append(fit(f"  {child.name}: {child.error}", width))
            continue
        try:
            child_map = research_map(base, child.name)
        except (OSError, ValueError) as error:
            lines.append(fit(f"  {child.name}: {error}", width))
            continue
        pending = sum(item.project == child.name for item in waiting)
        lines.append(fit(f"  {child.name}", width))
        lines.append(fit(f"    {track(child_map.stage, width - 4, glyphs)}", width))
        state = "data INVALID" if child_map.errors else f"{pending} to decide"
        first = child_map.moves[0].text if child_map.moves else ""
        lines.append(fit(f"    {state}; next: {first}", width))
    for message in report.errors:
        lines.append(fit(f"Error: {message}", width))
    return "\n".join(lines) + "\n"


def signature(folder: Path) -> tuple[tuple[str, int, int, int], ...]:
    """File metadata that changes when the map can change.

    Run archives are large and written by model sessions; only their top-level files
    (output.md, intake.md) matter, so they are not descended into. Hidden directories are
    skipped; hidden files such as an interrupted-writer lock are kept.
    """
    found: list[tuple[str, int, int, int]] = []

    def visit(path: Path, deep: bool) -> None:
        try:
            entries = sorted(os.scandir(path), key=lambda entry: entry.name)
        except OSError:
            return
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                if entry.name.startswith("."):
                    continue  # .git and tool folders; hidden lock files are still watched
                archive = path.name == "runs" and entry.name not in {"proposals", "drafts"}
                if deep:
                    visit(Path(entry.path), not archive)
                continue  # a directory's own metadata changes with its contents
            try:
                info = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            found.append((entry.path, info.st_size, info.st_mtime_ns, info.st_ino))

    visit(folder, True)
    return tuple(found)


def watch(
    draw: Callable[[], str],
    changed: Callable[[], object],
    interval: float,
    echo: Callable[[str], None],
    sleep: Callable[[float], None] = time.sleep,
    limit: int | None = None,
    clear: bool = True,
) -> int:
    """Redraw whenever ``changed()`` differs; return how many times the map was drawn."""
    last: object = None
    drawn = polls = 0
    while limit is None or polls < limit:
        current = changed()
        if polls == 0 or current != last:
            echo((CLEAR if clear else "") + draw())
            drawn += 1
            last = current
        polls += 1
        if limit is None or polls < limit:
            sleep(interval)
    return drawn


def terminal_width() -> int:
    return max(shutil.get_terminal_size((80, 24)).columns, 40)


def validate_claim(value: str | None) -> str | None:
    if value is None:
        return None
    return str(ObjectId.parse(value))
