"""YAML front matter with an opaque UTF-8 Markdown body."""

import io
from typing import Any

from toulmin.core.documents import Document, FormatError, validate_values


def load_restricted(
    text: str, location: str, first_line: int, label: str = "header"
) -> tuple[Any, dict[str, int]]:
    """Load YAML limited to plain data: no tags, anchors, aliases, directives or merges.

    `first_line` is the file line of the text's first line, so errors stay locatable.
    Returns the value and a map from field path to file line.
    """
    # Lazy imports keep the pure data/protocol modules importable without a parser.
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError
    from ruamel.yaml.nodes import MappingNode, SequenceNode
    from ruamel.yaml.tokens import AliasToken, AnchorToken, DirectiveToken, TagToken

    yaml = YAML(typ="safe", pure=True)
    lines: dict[str, int] = {}

    # Header paths are bare field names; other blocks prefix theirs, e.g. drafts[0].
    named = "" if label == "header" else label

    def inspect(node: Any, field: str = "") -> None:
        lines[field or "header"] = node.start_mark.line + first_line
        if isinstance(node, MappingNode):
            for key, value in node.value:
                path = f"{field}.{key.value}" if field else str(key.value)
                if key.value == "<<":
                    raise FormatError(
                        f"{location}:{key.start_mark.line + first_line}: {named}{path}: "
                        "merge keys forbidden"
                    )
                inspect(value, path)
        elif isinstance(node, SequenceNode):
            for index, value in enumerate(node.value):
                inspect(value, f"{field}[{index}]")

    try:
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, DirectiveToken, TagToken)):
                raise FormatError(
                    f"{location}:{token.start_mark.line + first_line}: {label}: "
                    "tags, anchors, aliases and directives forbidden"
                )
        node = yaml.compose(text)
        if node is not None:
            inspect(node)
        value = yaml.load(text)
    except (YAMLError, RecursionError) as error:
        mark = getattr(error, "problem_mark", None)
        line = mark.line + first_line if mark else first_line
        raise FormatError(f"{location}:{line}: {label}: {error}") from error
    return value, lines


def decode(data: bytes, location: str = "<memory>") -> Document:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise FormatError(f"{location}:1: encoding: expected UTF-8") from error
    if "\r" in text or not text.startswith("---\n"):
        raise FormatError(f"{location}:1: front_matter: expected LF and opening ---")
    header, separator, body = text[4:].partition("\n---\n")
    if not separator:
        raise FormatError(f"{location}:1: front_matter: missing closing ---")
    metadata, lines = load_restricted(header, location, 2)
    if not isinstance(metadata, dict):
        raise FormatError(f"{location}:2: header: expected mapping")
    document = Document(metadata, body, location, lines, header.count("\n") + 4)
    validate_values(document)
    return document


def encode(document: Document) -> bytes:
    from ruamel.yaml import YAML

    validate_values(document)
    yaml = YAML(typ="safe", pure=True)
    yaml.allow_unicode = True
    yaml.default_flow_style = False
    # Keep the caller's (contract) field order and never fold long strings, so generated
    # files read and diff like hand-written ones.
    yaml.width = 4096
    yaml.representer.sort_base_mapping_type_on_output = False
    stream = io.StringIO()
    yaml.dump(document.header, stream)
    return ("---\n" + stream.getvalue() + "---\n" + document.body).encode("utf-8")


def patch_header(data: bytes, changes: dict[str, Any], order: tuple[str, ...] = ()) -> bytes:
    """Edit selected metadata, retaining YAML comments/quotes and exact body bytes.

    A key that does not exist yet is inserted before the first existing key that follows
    it in `order` (appended when none does), so contract field order survives edits.
    """
    from ruamel.yaml import YAML

    decode(data)  # Apply the same restricted input syntax before round-trip loading.
    header, _, body = data.decode("utf-8")[4:].partition("\n---\n")
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    metadata = yaml.load(header)
    for key, value in changes.items():
        old = metadata.get(key)
        if isinstance(old, list) and isinstance(value, list) and value[: len(old)] == old:
            old.extend(value[len(old) :])
        elif key not in metadata and key in order:
            later = order[order.index(key) + 1 :]
            keys = list(metadata)
            position = next((keys.index(k) for k in keys if k in later), len(keys))
            metadata.insert(position, key, value)
        else:
            metadata[key] = value
    stream = io.StringIO()
    yaml.dump(metadata, stream)
    result = ("---\n" + stream.getvalue() + "---\n" + body).encode("utf-8")
    decode(result)
    return result
