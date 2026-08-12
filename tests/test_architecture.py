"""Structural rules, asserted against the source rather than trusted to memory.

These are the rules a type checker cannot see and an ordinary unit test cannot reach, because
nothing *breaks* when they are violated — the code still runs, it just stops being the shape it
was designed as. Layering decays silently, so it is checked mechanically on every run.

Two of these mirror ``scripts/check_frontend_rules.js``. That duplication is deliberate: the node
script is not part of ``pytest``, so a rule that lives only there is only enforced when somebody
remembers to run it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def python_files(package: str) -> list[Path]:
    return [p for p in (ROOT / package).rglob("*.py") if "__pycache__" not in p.parts]


def frontend_files() -> list[Path]:
    src = ROOT / "web" / "src"
    return [p for p in src.rglob("*.ts*") if p.suffix in {".ts", ".tsx"}] if src.is_dir() else []


# ------------------------------------------------------- the service layer stays framework-free
def imported_modules(path: Path) -> set[str]:
    """Top-level module names imported by a file, via AST rather than text matching.

    A regex over the source would also match the word inside a comment or a docstring, which is
    how this kind of test ends up either failing on prose or passing on a commented-out import.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("path", python_files("services"), ids=lambda p: p.name)
def test_no_service_imports_the_web_framework(path: Path):
    """``services/`` holds the business logic and must not know it is behind HTTP.

    The moment a service raises ``HTTPException`` or reads a ``Request``, it can only be called
    from a route — not from the evaluation harness, the experiment runner, a script or a test.
    Every one of those callers exists in this project, which is what makes the rule load-bearing
    rather than decorative.
    """
    offenders = imported_modules(path) & {"fastapi", "starlette"}
    assert not offenders, f"{path.name} imports {', '.join(sorted(offenders))}"


def test_the_service_layer_is_not_empty():
    """Guards the parametrised test above: no files means it passes without checking anything."""
    assert len(python_files("services")) >= 10


# ------------------------------------------------------------- exactly one module talks HTTP
def test_nothing_outside_the_api_client_calls_fetch():
    """One module owns the network, so auth headers and error handling cannot drift apart.

    Enforced here as well as in the node script, because ``pytest`` is what actually runs.
    """
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in frontend_files()
        if path.as_posix().endswith("lib/api.ts") is False
        and re.search(r"\bfetch\s*\(", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"call fetch directly: {', '.join(offenders)}"


def test_the_frontend_is_actually_present():
    """Same guard: an empty file list would make the rule above vacuous."""
    assert len(frontend_files()) >= 20
    assert (ROOT / "web" / "src" / "lib" / "api.ts").is_file()


# ------------------------------------------------------ ownership is checked in exactly one place
def test_only_one_module_defines_the_ownership_check():
    """Tenant isolation is a single chokepoint or it is nothing.

    If a second module grows its own "is this yours?" logic, the two drift and one of them
    eventually says yes when it should say no. The check is defined in ``api/deps.py`` and
    depended on everywhere else.
    """
    definitions = [
        path.relative_to(ROOT).as_posix()
        for path in python_files("api") + python_files("services")
        if re.search(r"^def get_owned_workspace", path.read_text(encoding="utf-8"), re.M)
    ]
    assert definitions == ["api/deps.py"], f"defined in: {definitions}"


@pytest.mark.parametrize(
    "router",
    [p for p in python_files("api/routers") if p.stem not in {"__init__", "auth"}],
    ids=lambda p: p.stem,
)
def test_every_workspace_router_uses_the_ownership_dependency(router: Path):
    """A workspace-scoped router that forgot the dependency would serve other users' data."""
    source = router.read_text(encoding="utf-8")
    assert "OwnedWorkspace" in source, f"{router.name} never depends on OwnedWorkspace"


# --------------------------------------------------------------------- no secrets in the source
@pytest.mark.parametrize("package", ["core", "db", "services", "api", "skills", "schemas"])
def test_no_provider_key_is_hard_coded(package: str):
    """A key committed to source is a key that has to be rotated, not merely edited out."""
    pattern = re.compile(r"(gsk_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|npg_[A-Za-z0-9]{10,})")
    for path in python_files(package):
        found = pattern.search(path.read_text(encoding="utf-8"))
        assert not found, f"{path.relative_to(ROOT)} contains something shaped like an API key"
