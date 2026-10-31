"""Pure entry-protocol planning; reading files belongs to the caller."""

from pathlib import PurePosixPath

from toulmin.core.identifiers import validate_project_name


def entry_files(project: str, latest_handoff: str | None = None) -> tuple[PurePosixPath, ...]:
    """Return resident context in protocol order, relative to the workbench root.

    PROJECT.md records the last applied handoff filename. A new project has none.
    This function neither scans a repository nor loads the project's objects.
    """
    project_dir = PurePosixPath("projects", validate_project_name(project))
    paths = (PurePosixPath("AGENTS.md"), project_dir / "PROJECT.md")
    if latest_handoff is None:
        return paths
    if (
        not latest_handoff.endswith(".md")
        or latest_handoff in {".md", "..md"}
        or "/" in latest_handoff
        or "\\" in latest_handoff
        or any(ord(character) < 32 for character in latest_handoff)
    ):
        raise ValueError("Handoff must be a Markdown filename inside sessions/")
    return (*paths, project_dir / "sessions" / latest_handoff)
