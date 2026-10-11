"""The converter as an installable package (pyproject.toml): RockForge installs it
under the name pdf_to_gp5, so app/ must keep importing its own modules relatively,
and every subpackage must be listed or it is left out of the install."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"


def _setuptools() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]


def test_every_subpackage_of_app_is_installed() -> None:
    config = _setuptools()
    assert config["package-dir"] == {"pdf_to_gp5": "app"}
    found = {
        ".".join(("pdf_to_gp5", *init.parent.relative_to(APP).parts))
        for init in APP.rglob("__init__.py")
        if "static" not in init.parts
    }
    assert set(config["packages"]) == found


def test_app_never_imports_itself_by_name() -> None:
    """Installed as pdf_to_gp5 there is no "app" to import: an absolute
    ``from app.x import y`` would work here and break in RockForge."""
    offenders = []
    for module in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            if any(name == "app" or name.startswith("app.") for name in names):
                offenders.append(f"{module.relative_to(ROOT)}:{node.lineno}")
    assert offenders == []
