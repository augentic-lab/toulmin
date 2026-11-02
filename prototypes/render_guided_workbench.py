"""Export actual Textual wireframe renders; never install assets or call models."""

import argparse
import asyncio
from pathlib import Path

from guided_workbench import GuidedWorkbench
from textual.widgets import Button


def capture(app: GuidedWorkbench, size: tuple[int, int], output: Path, name: str) -> None:
    if size == (120, 36) or name in {"explore", "validate", "resume"}:
        filename = f"{name}-{size[0]}.svg"
        app.save_screenshot(filename, str(output))
        # Rich exports a whitespace-only line that fails the repository diff check.
        path = output / filename
        path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")


async def render(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for size in ((120, 36), (80, 24), (60, 20)):
        app = GuidedWorkbench()
        async with app.run_test(size=size) as pilot:
            await pilot.pause()

            capture(app, size, output, "home")
            for key, name in (
                ("create", "setup"),
                ("initialize", "overview"),
                ("resume", "explore"),
                ("save-brief", "statements"),
                ("statement", "review-plan"),
                ("run-review", "triage"),
                ("record", "issue"),
                ("validate", "validate"),
                ("save-plan", "plan-saved"),
                ("end-session", "handoff"),
                ("save-handoff", "resume"),
            ):
                app.query_one(f"#{key}", Button).focus()
                await pilot.press("enter")
                await pilot.pause()
                capture(app, size, output, name)
    print(f"Exported wireframes to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    asyncio.run(render(parser.parse_args().output))
