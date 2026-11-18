"""Portable inspection policies preserve legacy definitions and pinned observations."""

import json
import tomllib
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256

import pytest

from toulmin.core.documents import FormatError
from toulmin.core.scope import Scope
from toulmin.core.sources import (
    InspectionPolicy,
    SourceAssociation,
    SourceCatalog,
    SourceDefinition,
    definition_data,
    parse_source_catalog,
    render_source_catalog,
)


def legacy_definition() -> SourceDefinition:
    return SourceDefinition("source-main", 1, "git", "git-roots-v1", "git:" + "a" * 64)


def catalog(definition: SourceDefinition) -> SourceCatalog:
    return SourceCatalog(2, (definition,), (SourceAssociation(Scope(), definition.id, "working"),))


def test_legacy_definition_bytes_and_hash_are_unchanged() -> None:
    definition = legacy_definition()
    fields = {
        "id": "source-main",
        "definition_revision": 1,
        "kind": "git",
        "identity_method": "git-roots-v1",
        "identity": "git:" + "a" * 64,
    }
    expected = (
        "schema_version = 2\n\n\n[[definitions]]\n"
        'id = "source-main"\n'
        "definition_revision = 1\n"
        'kind = "git"\n'
        'identity_method = "git-roots-v1"\n'
        f'identity = "git:{"a" * 64}"\n'
        "\n[[associations]]\n"
        'scope = { kind = "workspace" }\n'
        'source = "source-main"\n'
        'role = "working"\n'
    ).encode()
    digest_input = json.dumps(fields, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    assert definition.sha256 == sha256((digest_input + "\n").encode()).hexdigest()
    assert definition_data(definition) == fields
    assert render_source_catalog(catalog(definition)) == expected
    assert parse_source_catalog(expected) == catalog(definition)


def test_policy_round_trip_preserves_order_and_immutable_state() -> None:
    policy = InspectionPolicy(("README.md", "DefenceTools/symbolic_executor"), ("vendor",))
    data = policy.to_data()
    assert data == {
        "include": ["README.md", "DefenceTools/symbolic_executor"],
        "exclude": ["vendor"],
    }
    assert InspectionPolicy.from_data(data) == policy
    data["include"].append("unreviewed")
    assert policy.include == ("README.md", "DefenceTools/symbolic_executor")
    with pytest.raises(FrozenInstanceError):
        policy.include = ("changed",)


def test_revision_two_is_valid_toml_and_policy_changes_definition_hash() -> None:
    policy = InspectionPolicy(("README.md", "src"), ("src/generated",))
    definition = replace(legacy_definition(), definition_revision=2, inspection=policy)
    raw = render_source_catalog(catalog(definition))
    assert b'inspection = { include = ["README.md", "src"], exclude = ["src/generated"] }' in raw
    assert tomllib.loads(raw.decode())["definitions"][0]["inspection"] == policy.to_data()
    assert parse_source_catalog(raw) == catalog(definition)
    changed = replace(definition, inspection=InspectionPolicy(("src", "README.md"), ()))
    assert definition.sha256 != legacy_definition().sha256
    assert changed.sha256 != definition.sha256
    fields = definition_data(definition)
    assert fields["inspection"] == policy.to_data()
    expected = json.dumps(fields, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    assert definition.sha256 == sha256((expected + "\n").encode()).hexdigest()


def test_unicode_policy_renders_valid_toml_without_surrogate_escapes() -> None:
    policy = InspectionPolicy(("资料/😀",), ())
    definition = replace(legacy_definition(), definition_revision=2, inspection=policy)
    assert parse_source_catalog(render_source_catalog(catalog(definition))) == catalog(definition)


@pytest.mark.parametrize(
    "path",
    [
        "",
        " ",
        "/src",
        ".",
        "..",
        "src/..",
        "./src",
        "src/./file",
        "src//file",
        "src/",
        "src\\file",
        "C:/src",
        ":(glob)src",
        "src/*",
        "src/?",
        "src/[ab]",
        "src\x00file",
        "src\nfile",
        "src\x7ffile",
        "src\x85file",
        "src\ud800file",
        "a" * 1025,
    ],
)
@pytest.mark.parametrize("field", ["include", "exclude"])
def test_invalid_literal_prefixes_are_rejected(path: str, field: str) -> None:
    data = {"include": ["src"], "exclude": []}
    data[field] = [path]
    with pytest.raises(FormatError, match="inspection"):
        InspectionPolicy.from_data(data)


@pytest.mark.parametrize(
    "data",
    [
        None,
        [],
        {},
        {"include": ["src"]},
        {"include": ["src"], "exclude": [], "extra": []},
        {"include": [], "exclude": []},
        {"include": "src", "exclude": []},
        {"include": ("src",), "exclude": []},
        {"include": ["src"], "exclude": "vendor"},
        {"include": [True], "exclude": []},
        {"include": ["src"], "exclude": [1]},
        {"include": ["src", "src"], "exclude": []},
        {"include": ["src"], "exclude": ["vendor", "vendor"]},
        {"include": ["src", "src/lib"], "exclude": []},
        {"include": ["src/lib", "src"], "exclude": []},
        {"include": [f"src{i}" for i in range(33)], "exclude": []},
        {"include": ["src"], "exclude": [f"vendor{i}" for i in range(33)]},
    ],
)
def test_policy_shape_bounds_and_overlaps_are_validated(data: object) -> None:
    with pytest.raises(FormatError, match="inspection"):
        InspectionPolicy.from_data(data)


def test_limits_and_component_prefixes_are_accepted() -> None:
    includes = tuple(["a" * 1024, *(f"src{i}" for i in range(31))])
    excludes = tuple(f"vendor{i}" for i in range(32))
    assert InspectionPolicy(includes, excludes).include == includes
    assert InspectionPolicy(("src", "src2"), ("src/vendor", "src/vendor/cache"))
    assert InspectionPolicy(("资料/目录",), ())


def test_constructor_refuses_mutable_collections() -> None:
    with pytest.raises(FormatError, match="immutable"):
        InspectionPolicy(["src"], ())


@pytest.mark.parametrize(
    "definition",
    [
        replace(legacy_definition(), definition_revision=True),
        replace(legacy_definition(), definition_revision=0),
        replace(legacy_definition(), definition_revision=3),
        replace(legacy_definition(), definition_revision=2),
        replace(legacy_definition(), inspection=InspectionPolicy(("src",), ())),
        SourceDefinition(
            "source-main",
            2,
            "directory",
            "directory-anchors-v1",
            "directory:" + "a" * 64,
            InspectionPolicy(("src",), ()),
        ),
    ],
)
def test_invalid_definition_policy_revision_combinations_are_rejected(
    definition: SourceDefinition,
) -> None:
    with pytest.raises(FormatError):
        render_source_catalog(catalog(definition))


def test_unknown_definition_and_policy_fields_are_rejected() -> None:
    definition = replace(
        legacy_definition(), definition_revision=2, inspection=InspectionPolicy(("src",), ())
    )
    raw = render_source_catalog(catalog(definition))
    for changed in (
        raw.replace(b"exclude = []", b"exclude = [], unknown = []"),
        raw.replace(b"inspection =", b"unknown = 1\ninspection ="),
        raw.replace(b'include = ["src"]', b"include = true"),
    ):
        with pytest.raises(FormatError):
            parse_source_catalog(changed)
