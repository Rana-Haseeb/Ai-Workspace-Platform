"""Every module in the project imports cleanly.

Cheap, but it earns its place: the Week 4 services were copied in with imports pointing at a
package (``app.*``) that does not exist here, and a broken import in a module nothing has wired
up yet is invisible until the phase that needs it. This catches that on every run.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ["core", "db", "schemas", "services", "skills", "api"]


def _module_names() -> list[str]:
    names: list[str] = []
    for package in PACKAGES:
        path = ROOT / package
        if not path.is_dir():
            continue
        names.append(package)
        for info in pkgutil.walk_packages([str(path)], prefix=f"{package}."):
            names.append(info.name)
    return names


@pytest.mark.parametrize("module_name", _module_names())
def test_module_imports(module_name: str):
    importlib.import_module(module_name)
