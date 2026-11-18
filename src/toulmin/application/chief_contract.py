"""Validate frozen engineering authority against Chief's mutable lifecycle (L3)."""

import re
from pathlib import Path
from typing import Any

from toulmin.application.sources import _git
from toulmin.core.documents import FormatError


def validate_lineage(repo: str, base: str, head: str) -> None:
    """Require exact, available commits and an ancestor chain; never run checks."""
    for revision in (base, head):
        if (
            not isinstance(revision, str)
            or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision)
            or _git(
                Path(repo), "rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"
            )
            != revision
        ):
            raise FormatError("Chief task lineage requires available full commit identities")
    if _git(Path(repo), "merge-base", "--is-ancestor", base, head) is None:
        raise FormatError("Chief task commit lineage is unrelated or unavailable")


def _protections(value: object) -> set[str]:
    if not isinstance(value, list) or any(
        not isinstance(path, str)
        or path.startswith("/")
        or "\\" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or any(ord(c) < 32 for c in path)
        for path in value
    ):
        raise FormatError("Chief task protected must contain portable repository-relative paths")
    return set(value)


def validate_chief_contract(existing: dict[str, Any], contract: dict[str, Any]) -> str:
    """Return Chief's scope base while retaining the original source baseline.

    approve_tests preserves base_branch, advances base to the approved HEAD and
    appends protected tests. Older sparse records can prove the unchanged baseline
    with base alone; an advanced base needs the complete immutable contract and
    the explicit test-first/build transition. No permission or scientific ruling
    is inferred here, and no external state is repaired.
    """
    repo, baseline, base = contract.get("repo"), contract.get("base_branch"), existing.get("base")
    if (
        not isinstance(repo, str)
        or not isinstance(baseline, str)
        or not isinstance(base, str)
        or not base
        or existing.get("repo") != repo
    ):
        raise FormatError("existing Chief task repo/baseline differs from frozen contract")
    if "base_branch" in existing and existing["base_branch"] != baseline:
        raise FormatError("existing Chief task base_branch differs from frozen contract")
    approved = (
        contract.get("test_first") is True
        and existing.get("test_first") is True
        and existing.get("phase") == "build"
    )
    advanced = base != baseline
    if advanced and (
        not approved
        or existing.get("base_branch") != baseline
        or not contract.keys() <= existing.keys()
    ):
        raise FormatError(
            "advanced Chief scope base requires complete frozen contract and "
            "test-first build lineage"
        )
    for key, value in contract.items():
        if key not in existing:
            continue  # Older Chief records may omit optional contract metadata.
        if key == "protected":
            frozen, current = _protections(value), _protections(existing[key])
            if not frozen <= current or (current != frozen and not approved):
                raise FormatError("Chief task protected weakens or changes frozen protections")
        elif existing[key] != value or (
            isinstance(value, bool) and type(existing[key]) is not bool
        ):
            raise FormatError(f"existing Chief task {key} differs from frozen contract")
    if advanced:
        validate_lineage(repo, baseline, base)
    return base
