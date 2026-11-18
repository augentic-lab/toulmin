"""Legacy source packets must not discard workspace definitions or focused policies."""

import pytest

from toulmin.core.documents import FormatError
from toulmin.core.scope import Scope
from toulmin.core.sources import (
    CATALOG,
    InspectionPolicy,
    Source,
    SourceAssociation,
    SourceCatalog,
    SourceDefinition,
    render_catalog,
    render_source_catalog,
)
from toulmin.core.workspace_journal import Image
from toulmin.protocols.context_change import _validate_images


def images():
    source = Source("source-main", "demo", "git", "working", "git:" + "a" * 64)
    old = render_catalog((source,))
    definition = SourceDefinition(
        source.source_id,
        2,
        "git",
        "git-roots-v1",
        source.identity,
        InspectionPolicy(("component",), ()),
    )
    focused = render_source_catalog(
        SourceCatalog(
            2,
            (definition,),
            (
                SourceAssociation(Scope(), source.source_id, "working"),
                SourceAssociation(Scope("demo"), source.source_id, "working"),
            ),
        )
    )
    return old, focused


@pytest.mark.parametrize("side", ["before", "after"])
def test_legacy_role_packet_cannot_cross_v2_catalog_boundary(side):
    old, focused = images()
    image = Image(
        CATALOG, focused if side == "before" else old, focused if side == "after" else old
    )
    with pytest.raises(FormatError, match="schema_version = 1"):
        _validate_images("demo", "source-role", [image])


def test_existing_legacy_role_packet_remains_valid():
    old, _ = images()
    _validate_images("demo", "source-role", [Image(CATALOG, old, old)])
