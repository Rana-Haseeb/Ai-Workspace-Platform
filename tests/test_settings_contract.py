"""Every setting the code reads actually exists on Settings.

This exists because of a real failure. Porting the Week 4 config dropped five fields the ported
``llm_service`` and ``usage`` still referenced. Nothing caught it: the imports were fine, the
type checker had nothing to check, and the attributes are only touched *during a model call* —
so the first sign was a 500 on the live gate.

A static scan for ``settings.<name>`` closes that gap in one cheap test.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.config import Settings, settings

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ["core", "db", "services", "skills", "api", "eval", "experiments"]

# `settings.` followed by an identifier, but only where `settings` is the module-level config
# singleton — never `workspace.settings.use_memory`, which is the AssistantSettings *row*.
#
# The two are genuinely different objects that happen to share a name: `core.config.settings` is
# deployment configuration, `workspace.settings` is the per-workspace assistant row. The negative
# lookbehind is what keeps this test from reporting the row's columns as missing config.
REFERENCE = re.compile(r"(?<![.\w])settings\.([a-z_][a-z0-9_]*)")


def _referenced_names() -> dict[str, set[str]]:
    """``{attribute: {files that use it}}`` across the whole codebase."""
    found: dict[str, set[str]] = {}
    for package in PACKAGES:
        directory = ROOT / package
        if not directory.is_dir():
            continue
        for path in directory.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for name in REFERENCE.findall(path.read_text(encoding="utf-8")):
                found.setdefault(name, set()).add(str(path.relative_to(ROOT)))
    return found


def test_every_referenced_setting_exists():
    fields = set(Settings.model_fields)
    methods = {name for name in dir(settings) if not name.startswith("_")}
    known = fields | methods

    missing = {
        name: sorted(files)
        for name, files in _referenced_names().items()
        if name not in known
    }
    assert not missing, "settings attributes referenced but not defined: " + repr(missing)


def test_the_scan_actually_finds_something():
    """Guards the guard: a regex that matches nothing would make the test above vacuous."""
    assert len(_referenced_names()) > 5


@pytest.mark.parametrize(
    "name",
    [
        "agent_timeout_seconds",
        "min_call_interval_seconds",
        "max_agent_calls_per_run",
        "max_run_seconds",
        "max_cost_usd_per_run",
    ],
)
def test_the_five_fields_that_were_dropped_in_the_port(name: str):
    """Named explicitly so a future tidy-up cannot quietly remove them again."""
    assert hasattr(settings, name)
