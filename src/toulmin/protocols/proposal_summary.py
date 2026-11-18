"""L2: a short summary of a pending proposal for ``toulmin decide`` (UX6).

Reason for this L2 addition (docs/protocols.md, UX6): decide printed every proposal in full,
including object bodies and frozen contracts, so each decision began with a page of reading.
The summary is plain text shaping over the exact bytes decide previews: a few header facts,
the first sentence of the main section and of the Why section. It never replaces the full
text, which stays one key away, and nothing is read from or written to files here.
"""

import re
from dataclasses import dataclass

FACT_KEYS = (
    "type",
    "importance",
    "target",
    "direction",
    "kind",
    "grade",
    "severity",
    "object",
    "objects",
    "status",
    "stage",
    "spec",
    "tool",
    "command",
    "repo",
)
MAIN_SECTIONS = (
    "Statement",
    "Content",
    "Material",
    "Choice",
    "Summary",
    "Requirements",
    "Goal",
    "Text",
    "Response",
    "Ruling",
    "Invalidation",
    "Rationale",
)
FACT_LIMIT = 60  # longer header values (plans, prompts) belong to the full text
HEADING = re.compile(r"^#{2,3} +(.+?) *$")


@dataclass(frozen=True)
class Summary:
    facts: tuple[tuple[str, str], ...]  # (key, value) from the header, in FACT_KEYS order
    main: tuple[str, str] | None  # (section, its first paragraph on one line)
    why: str | None  # first paragraph of a Why section


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            header = lines[1:index]
            body = "\n".join(lines[index + 1 :])
            break
    else:
        return {}, text
    values: dict[str, str] = {}
    for line in header:
        if line[:1].isspace() or ":" not in line:
            continue  # nested YAML stays in the full text
        key, _, value = line.partition(":")
        value = value.strip().strip("\"'")
        if value and value not in {"|", ">", "|-", ">-"}:
            values[key.strip()] = value
    return values, body


def _sections(body: str) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in body.splitlines():
        match = HEADING.match(line)
        if match:
            current = found.setdefault(match.group(1), [])
            continue
        if current is not None:
            current.append(line)
    result = {}
    for name, lines in found.items():
        paragraph: list[str] = []
        for line in lines:
            if line.strip():
                paragraph.append(line.strip())
            elif paragraph:
                break
        if paragraph:
            result[name] = " ".join(paragraph)
    return result


def proposal_summary(text: str) -> Summary:
    """Header facts, the main section and the Why section of one proposal's text."""
    header, body = _front_matter(text)
    facts = tuple(
        (key, header[key])
        for key in FACT_KEYS
        if key in header
        and len(header[key]) <= FACT_LIMIT
        and not (key == "kind" and header[key].endswith("-proposal"))  # the label says it
    )
    sections = _sections(body)
    main = next(
        ((name, sections[name]) for name in MAIN_SECTIONS if name in sections),
        None,
    )
    if main is None:
        main = next(((name, value) for name, value in sections.items() if name != "Why"), None)
    return Summary(facts, main, sections.get("Why"))
