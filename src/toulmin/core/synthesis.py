"""L1 cross-validation answers and synthesis blocks, with no filesystem access.

A cross-validation answer ends with a yaml list of labelled points; a synthesis ends
with a yaml list of groups that cite every input item exactly once as ``R-NNN/label``.
Synthesis is commentary on archived outputs: it never becomes an object, and intake
always goes back to the original Run and label it cites.
"""

import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, NoReturn

from toulmin.core.documents import Document, FormatError, headings
from toulmin.core.identifiers import ObjectKind
from toulmin.core.review import LABEL, final_yaml_list
from toulmin.core.schema import reference

GROUP_KINDS = ("disagreement", "agreement", "singleton")
ITEM = re.compile(r"(R-\d{3,})/([A-Za-z0-9][A-Za-z0-9_-]{0,63})")
POINT_FIELDS = {"label", "position", "grounds"}
Fail = Callable[[str, str], NoReturn]
GROUP_FIELDS = {"group", "kind", "drafts", "note"}


@dataclass(frozen=True)
class Point:
    label: str
    position: str
    grounds: str
    uncertainty: str | None
    target: str | None
    line: int


@dataclass(frozen=True)
class Group:
    group: str
    kind: str
    items: tuple[str, ...]  # R-NNN/label
    target: str | None
    note: str
    line: int


def _checker(location: str, name: str, field: str, line: int) -> Fail:
    def fail(key: str, message: str) -> NoReturn:
        raise FormatError(f"{location}:{line}: {name}{field}.{key}: {message}")

    return fail


def _fields(item: Any, fail: Fail, required: set[str], optional: set[str]) -> dict[str, Any]:
    if not isinstance(item, dict):
        fail("", "expected mapping")
    for key in sorted(required - item.keys()):
        fail(key, "required field missing")
    for key in sorted(item.keys() - required - optional):
        fail(str(key), "unknown field")
    mapping: dict[str, Any] = item
    return mapping


def _text(item: dict[str, Any], key: str, fail: Fail) -> str:
    value = item[key]
    if not isinstance(value, str) or not value.strip():
        fail(key, "expected nonempty string")
    if headings(value.splitlines(keepends=True)):
        fail(key, "level-two headings are not allowed in block text")
    return str(value).strip()


def _claim(item: dict[str, Any], fail: Fail, location: str, line: int) -> str | None:
    if "target" not in item:
        return None
    holder = Document({}, "", location, {"": line}, line)
    try:
        target = reference(holder, item["target"], "target", ObjectKind.CLAIM)
    except FormatError as error:
        fail("target", str(error).rsplit(": ", 1)[-1])
    if target.project is not None:
        fail("target", "expected a Claim in this project")
    return str(item["target"])


def parse_points(raw: str, location: str) -> tuple[Point, ...]:
    """Parse the final yaml block of a cross-validation answer."""
    value, positions, first = final_yaml_list(raw, location, "points")
    points: list[Point] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        line = positions.get(f"[{index}]", first)
        fail = _checker(location, "points", f"[{index}]", line)
        item = _fields(item, fail, POINT_FIELDS, {"uncertainty", "target"})
        label = _text(item, "label", fail)
        if not LABEL.fullmatch(label):
            fail("label", "expected ASCII letters, digits, '_' or '-'")
        if label in seen:
            fail("label", f"duplicate label {label}")
        seen.add(label)
        points.append(
            Point(
                label,
                _text(item, "position", fail),
                _text(item, "grounds", fail),
                _text(item, "uncertainty", fail) if "uncertainty" in item else None,
                _claim(item, fail, location, line),
                line,
            )
        )
    return tuple(points)


def parse_synthesis(raw: str, location: str, known: Collection[str]) -> tuple[Group, ...]:
    """Parse a synthesis block; every known ``R-NNN/label`` must be grouped exactly once."""
    value, positions, first = final_yaml_list(raw, location, "groups")
    groups: list[Group] = []
    names: set[str] = set()
    placed: dict[str, str] = {}
    for index, item in enumerate(value):
        line = positions.get(f"[{index}]", first)
        fail = _checker(location, "groups", f"[{index}]", line)
        item = _fields(item, fail, GROUP_FIELDS, {"target"})
        name = _text(item, "group", fail)
        if not LABEL.fullmatch(name):
            fail("group", "expected ASCII letters, digits, '_' or '-'")
        if name in names:
            fail("group", f"duplicate group {name}")
        names.add(name)
        if item["kind"] not in GROUP_KINDS:
            fail("kind", f"expected one of {GROUP_KINDS}")
        cited = item["drafts"]
        if not isinstance(cited, list) or not cited:
            fail("drafts", "expected a nonempty list of R-NNN/label")
        for entry in cited:
            if not isinstance(entry, str) or not ITEM.fullmatch(entry):
                fail("drafts", f"{entry!r}: expected R-NNN/label")
            if entry not in known:
                fail("drafts", f"{entry} is not an item of this round")
            if entry in placed:
                fail("drafts", f"{entry} already placed in group {placed[entry]}")
            placed[entry] = name
        runs = {entry.split("/", 1)[0] for entry in cited}
        if item["kind"] == "singleton" and len(cited) != 1:
            fail("drafts", "a singleton cites exactly one item")
        if item["kind"] != "singleton" and len(runs) < 2:
            fail("drafts", f"{item['kind']} groups cite items from at least two Runs")
        groups.append(
            Group(
                name,
                item["kind"],
                tuple(cited),
                _claim(item, fail, location, line),
                _text(item, "note", fail),
                line,
            )
        )
    missing = [entry for entry in known if entry not in placed]
    if missing:
        shown = ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")
        raise FormatError(f"{location}:{first}: groups: items not grouped: {shown}")
    return tuple(groups)
