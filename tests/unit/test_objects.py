import pytest

from toulmin.core.codec import decode, encode
from toulmin.core.documents import FormatError
from toulmin.core.identifiers import ObjectKind
from toulmin.core.repository import Repository
from toulmin.core.schema import validate


@pytest.mark.parametrize("kind", list(ObjectKind))
def test_every_documented_example_validates_and_round_trips(example_docs, kind):
    document = example_docs[kind]
    validate(document)
    reread = decode(encode(document))
    validate(reread)
    assert reread.header == document.header
    assert reread.body.encode() == document.body.encode()


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("claim", "type", "workload"),
        ("run", "status", "running"),
        ("evidence", "grade", "verified"),
        ("objection", "target", "E-001"),
        ("decision", "related", []),
        ("exploration", "status", "adopted"),
        ("spec", "target", "X-001"),
    ],
)
def test_each_documented_invalid_variant_is_rejected(example_docs, kind, field, value):
    document = example_docs[ObjectKind(kind)]
    document.header[field] = value
    with pytest.raises(FormatError):
        validate(document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("schema_version", "1"),
        ("id", "C-1"),
        ("id", None),
        ("status", ["proposed"]),
        ("status", {}),
        ("created", "2026-10-31"),
        ("created", "2026-10-31T10:00:00"),
        ("created", "2026-13-31T10:00:00Z"),
        ("type", True),
        ("importance", "critical"),
        ("tags", "workload"),
        ("tags", [3]),
        ("validation_plan", " "),
        ("source", []),
        ("source", {"kind": "human"}),
        ("source", {"kind": "model", "actor": "reviewer"}),
        ("source", {"kind": "human", "actor": "X", "ref": "R-001"}),
        ("confirmed_by", {"actor": "X"}),
        ("confirmed_by", {"actor": "", "at": "2026-10-31T10:00:00Z"}),
        ("extensions", {"unnamespaced": "value"}),
        ("extensions", []),
        ("decisions", ["C-001"]),
        ("unknown", "value"),
    ],
)
def test_bad_common_or_claim_fields_have_source_and_field_diagnostics(example_docs, field, value):
    doc = example_docs[ObjectKind.CLAIM]
    doc.header[field] = value
    with pytest.raises(FormatError) as raised:
        validate(doc)
    assert "format-examples.md:" in str(raised.value)
    assert field.split(".")[0] in str(raised.value)


@pytest.mark.parametrize(
    "extra",
    [
        "id: C-002",
        "x: &name value",
        "x: *name",
        "x: !!str value",
        "x: !custom value",
        "<<: {other: value}",
        "x: .inf",
        "x: .nan",
        "x: {1: value}",
        "x: 2026-10-31",
    ],
)
def test_unapproved_yaml_constructs_are_rejected_before_schema_validation(example_docs, extra):
    raw = encode(example_docs[ObjectKind.CLAIM]).replace(
        b"\n---\n", ("\n" + extra + "\n---\n").encode(), 1
    )
    with pytest.raises(FormatError) as raised:
        decode(raw, "bad.md")
    assert "bad.md:" in str(raised.value)


@pytest.mark.parametrize(
    "raw",
    [
        b"no header",
        b"---\nkey: value\nbody",
        b"---\n[]\n---\nbody",
        b"---\r\nid: C-001\r\n---\r\nbody",
        b"\xff",
        b"---\n%YAML 1.2\n---\na: b\n---\nbody",
    ],
)
def test_invalid_front_matter_is_not_silently_treated_as_body(raw):
    with pytest.raises(FormatError):
        decode(raw, "bad.md")


def test_body_preserves_unicode_rules_and_code_fences(example_docs):
    document = example_docs[ObjectKind.CLAIM]
    document.body += (
        "\n---\n中文正文\n```markdown\n## Statement\n---\n```\n~~~text\n## Statement\n~~~\n"
    )
    validate(document)
    assert decode(encode(document)).body == document.body
    document.body += "\n## Statement\nDuplicate statement\n"
    with pytest.raises(FormatError, match="duplicate section"):
        validate(document)


def test_body_diagnostics_report_the_actual_markdown_line(example_docs):
    document = example_docs[ObjectKind.CLAIM]
    raw = encode(document).decode() + "\n## Statement\nDuplicate\n"
    expected_line = raw.splitlines().index("Duplicate")
    reread = decode(raw.encode(), "claim.md")
    with pytest.raises(FormatError, match=f"claim.md:{expected_line}: body.Statement"):
        validate(reread)


@pytest.mark.parametrize(
    "kind,status,field",
    [
        ("claim", "accepted", "decisions"),
        ("claim", "refuted", "decisions"),
        ("objection", "answered", "Response"),
        ("objection", "deferred", "Ruling"),
        ("decision", "superseded", "superseded_by"),
        ("exploration", "dropped", "Rationale"),
        ("spec", "passed", "evidence"),
        ("run", "failed", "Failure"),
        ("evidence", "invalidated", "Invalidation"),
    ],
)
def test_status_specific_obligations(example_docs, kind, status, field):
    document = example_docs[ObjectKind(kind)]
    document.header["status"] = status
    with pytest.raises(FormatError, match=field):
        validate(document)


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("evidence", "provenance", []),
        ("evidence", "provenance", [{"description": "source"}]),
        ("evidence", "provenance", [{"description": "source", "url": "file:///tmp/file"}]),
        ("evidence", "provenance", [{"description": "source", "url": "https://x", "path": "x"}]),
        ("evidence", "verification", {"method": "code", "result": "pass", "artifacts": []}),
        ("run", "duration_seconds", True),
        ("run", "duration_seconds", -1),
        ("run", "duration_seconds", "3"),
        ("run", "session_id", ""),
        ("run", "input_files", [None]),
    ],
)
def test_bad_evidence_and_run_fields(example_docs, kind, field, value):
    document = example_docs[ObjectKind(kind)]
    document.header[field] = value
    with pytest.raises(FormatError, match=field):
        validate(document)


def test_valid_verified_evidence_and_optional_extensions(example_docs):
    document = example_docs[ObjectKind.EVIDENCE]
    document.header.update(
        grade="verified",
        verification={
            "method": "computation",
            "result": "see artifact",
            "artifacts": ["runs/results.csv"],
        },
    )
    document.header["extensions"] = {"test.repetitions": 3}
    validate(document)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "not a string key"}, object()])
def test_api_created_extensions_obey_the_same_value_restrictions(example_docs, value):
    document = example_docs[ObjectKind.CLAIM]
    document.header["extensions"] = {"test.value": value}
    with pytest.raises(FormatError, match="extensions"):
        validate(document)


def test_source_run_can_be_resolved_in_another_project(populated, example_docs):
    from toulmin.cli.initialize import initialize

    initialize(populated, "second")
    output = populated / "projects/second/runs/20261031T100000Z-review"
    output.mkdir()
    (output / "output.md").write_text("Fixture: second project's raw review\n")
    run = example_docs[ObjectKind.RUN]
    run.header["output"] = "projects/second/runs/20261031T100000Z-review"
    (populated / "projects/second/runs/R-001.md").write_bytes(encode(run))
    objection = example_docs[ObjectKind.OBJECTION]
    objection.header["source"].update(
        ref="second/R-001", path="projects/second/runs/20261031T100000Z-review/output.md"
    )
    Repository(populated).validate_links(objection, "demo")


def test_direct_cross_references_of_all_examples_resolve(populated, example_docs):
    repository = Repository(populated)
    for doc in example_docs.values():
        reread = repository.load("demo", doc.object_id)
        repository.validate_links(reread, "demo")


@pytest.mark.parametrize(
    "field,value",
    [
        ("target", "C-999"),
        ("target", "missing/C-001"),
        ("source.ref", "R-999"),
        ("source.path", "projects/demo/brief.md"),
        ("source.path", "../outside.md"),
        ("source.path", "projects/demo/runs/missing.md"),
    ],
)
def test_missing_links_or_wrong_run_archives_reject_intake(populated, example_docs, field, value):
    document = example_docs[ObjectKind.OBJECTION]
    if "." in field:
        parent, child = field.split(".")
        document.header[parent][child] = value
    else:
        document.header[field] = value
    validate(document)
    with pytest.raises(FormatError, match=field.replace(".", r"\.")):
        Repository(populated).validate_links(document, "demo")


def test_provenance_and_verification_artifacts_must_exist(populated, example_docs):
    document = example_docs[ObjectKind.EVIDENCE]
    document.header["provenance"] = [{"description": "missing", "path": "missing.csv"}]
    validate(document)
    with pytest.raises(FormatError, match="provenance"):
        Repository(populated).validate_links(document, "demo")
    document.header["provenance"] = [
        {"description": "remote", "url": "https://example.invalid/paper"}
    ]
    document.header.update(
        grade="verified",
        verification={"method": "code", "result": "test", "artifacts": ["missing.csv"]},
    )
    with pytest.raises(FormatError, match="artifacts"):
        Repository(populated).validate_links(document, "demo")


def test_run_cannot_point_to_another_projects_output_or_missing_input(populated, example_docs):
    document = example_docs[ObjectKind.RUN]
    document.header["output"] = "global"
    with pytest.raises(FormatError, match="output"):
        Repository(populated).validate_links(document, "demo")
    document.header["output"] = "projects/demo/runs/20261031T100000Z-review"
    document.header["input_files"] = ["missing.md"]
    with pytest.raises(FormatError, match="input_files"):
        Repository(populated).validate_links(document, "demo")


@pytest.mark.parametrize("name", ["not-dated", "20261331T100000Z-review"])
def test_run_archive_names_include_a_valid_utc_timestamp(populated, example_docs, name):
    document = example_docs[ObjectKind.RUN]
    relative = "projects/demo/runs/" + name
    (populated / relative).mkdir()
    document.header["output"] = relative
    with pytest.raises(FormatError, match="output"):
        Repository(populated).validate_links(document, "demo")
