"""Dependency conventions, plus execution without any installed CLI libraries."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src"

# An intentional allowlist makes adding a dependency a reviewable change.
# This is an architecture check, not a sandbox for arbitrary hostile Python.
DATA_MODULES = {
    "collections",
    "contextlib",
    "dataclasses",
    "datetime",
    "enum",
    "fcntl",
    "hashlib",
    "io",
    "math",
    "os",
    "pathlib",
    "re",
    "ruamel",
    "shutil",
    "tempfile",
    "typing",
    "uuid",
}


def violations(source: str, package: str) -> list[str]:
    allowed_layers = ("toulmin.core",)
    if package.startswith("toulmin.protocols"):
        allowed_layers += ("toulmin.protocols",)
    errors = []
    for node in ast.walk(ast.parse(source)):
        modules = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                parents = package.split(".")
                if node.level > len(parents):
                    errors.append("relative import escapes package")
                    continue
                prefix = ".".join(parents[: len(parents) - node.level + 1])
                module = f"{prefix}.{module}".rstrip(".")
            modules = [module]
            if module == "os" and any(
                alias.name in {"system", "popen", "spawnl", "spawnv", "execv", "execve"}
                for alias in node.names
            ):
                errors.append("external command import")
        for module in modules:
            internal = any(
                module == layer or module.startswith(layer + ".") for layer in allowed_layers
            )
            if not internal and module.partition(".")[0] not in DATA_MODULES:
                errors.append(f"forbidden import: {module}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"__import__", "eval", "exec"}:
                errors.append(f"dynamic execution: {node.func.id}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"system", "popen", "execv", "execve", "spawnl", "spawnv"}:
                errors.append("external command call")
    return errors


def test_core_and_protocol_dependencies_point_downward():
    for layer in ("core", "protocols"):
        for path in (SOURCE / "toulmin" / layer).rglob("*.py"):
            package = ".".join(path.relative_to(SOURCE).parent.parts)
            assert not violations(path.read_text(), package), path
    assert not violations((SOURCE / "toulmin" / "__init__.py").read_text(), "toulmin")


@pytest.mark.parametrize(
    "source,package",
    [
        ("import typer", "toulmin.core"),
        ("from toulmin.cli import app", "toulmin.core"),
        ("from ..cli import app", "toulmin.core"),
        ("from toulmin import cli", "toulmin.core"),
        ("from ..protocols import session", "toulmin.core"),
        ("import subprocess as process; process.run(['model'])", "toulmin.core"),
        ("from os import system as shell; shell('model')", "toulmin.core"),
        ("__import__('typer')", "toulmin.core"),
        ("import toulmin.adapters", "toulmin.protocols"),
    ],
)
def test_dependency_guard_detects_regressions(source, package):
    assert violations(source, package)


def test_dependency_guard_allows_l2_to_use_l1():
    assert not violations("from ..core.identifiers import ObjectId", "toulmin.protocols")


def test_core_and_protocols_work_without_site_packages_or_cli(tmp_path):
    script = """
import importlib
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])

class BlockAdapters:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('typer', 'click', 'toulmin.cli', 'toulmin.adapters')):
            raise ImportError('adapter unavailable: ' + fullname)

sys.meta_path.insert(0, BlockAdapters())
for layer in ('core', 'protocols'):
    for file in (Path(sys.argv[1]) / 'toulmin' / layer).rglob('*.py'):
        parts = file.relative_to(sys.argv[1]).with_suffix('').parts
        module = '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)
        importlib.import_module(module)
from toulmin.core.identifiers import ObjectRef
from toulmin.protocols.session import entry_files
assert str(ObjectRef.parse('demo/C-001')) == 'demo/C-001'
assert str(entry_files('demo')[1]) == 'projects/demo/PROJECT.md'
assert not any(name.startswith(('typer', 'click', 'toulmin.cli')) for name in sys.modules)
print('portable')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script, str(SOURCE)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "portable"


def test_confirmed_intake_can_execute_with_adapters_unavailable(workbench):
    script = """
import sys
from pathlib import Path
class BlockAdapters:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('typer', 'click', 'toulmin.cli', 'toulmin.adapters')):
            raise ImportError('adapter unavailable: ' + fullname)
sys.meta_path.insert(0, BlockAdapters())
from toulmin.core.codec import encode
from toulmin.core.documents import Document
from toulmin.core.identifiers import ObjectKind
from toulmin.protocols.intake import create_object
root = Path(sys.argv[1])
relative = 'projects/demo/runs/portable/draft.md'
path = root / relative
path.parent.mkdir()
path.write_bytes(encode(Document(
    {'source': {'kind': 'human', 'actor': 'Researcher'}, 'type': 'problem', 'importance': 'core'},
    '## Statement\\nA test fixture claim.\\n',
)))
created = create_object(root, 'demo', ObjectKind.CLAIM, relative, 'Researcher', True)
assert created.name == 'C-001.md'
assert not any(name.startswith(('typer', 'click', 'toulmin.cli')) for name in sys.modules)
print('portable intake')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(workbench)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "portable intake"
