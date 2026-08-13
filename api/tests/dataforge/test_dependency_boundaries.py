"""Guard tests for two properties that are easy to lose by accident.

Both exist to keep this package portable into a host application:

  - pandas is gone. It was carried for positional cell reads that openpyxl
    already does, and it is a heavy dependency for a tool that installs into a
    user account with no admin rights. One `import pandas` in a future edit
    quietly puts it back.

  - Only the web layer knows about the web framework. Everything else is
    plain Python, so moving this package under a different host means
    rewriting one file rather than untangling the parsers.

These are properties, not behavior, so they are checked by reading the source
rather than by running it.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "dataforge"
FRAMEWORKS = {"flask", "fastapi", "django", "starlette"}
BANNED = {"pandas", "numpy"}


def _modules():
    return sorted(p for p in PACKAGE.glob("*.py"))


def _imported_roots(path: Path) -> set:
    """Top-level package name of every import in a module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import, which has no external root.
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_the_package_has_modules_to_check():
    """Guard the guard: a path typo would make every test below vacuous."""
    names = [p.name for p in _modules()]
    assert "eduphoria_parser.py" in names
    assert "views.py" in names


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_no_banned_dependency(path):
    leaked = _imported_roots(path) & BANNED
    assert not leaked, (
        f"{path.name} imports {sorted(leaked)}. These were removed deliberately; "
        "use dataforge.tabular for spreadsheet and CSV reading."
    )


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_only_the_web_layer_imports_a_web_framework(path):
    found = _imported_roots(path) & FRAMEWORKS
    assert not found, (
        f"{path.name} imports {sorted(found)}. No module under api/dataforge/ "
        "may import a web framework."
    )


def test_requirements_do_not_list_a_banned_dependency():
    req = (PACKAGE.parent / "requirements.txt").read_text(encoding="utf-8").lower()
    for name in BANNED:
        assert name not in req, f"requirements.txt still lists {name}"


def test_requirements_declare_openpyxl_runtime_dependency():
    req = (PACKAGE.parent / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "openpyxl>=3.1,<4" in req
