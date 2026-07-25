"""Keep workspace.py and lib_inventory.py agreeing on one package slug.

``workspace.py --skill research-lib`` derives
``.agents/docs/libraries/{slug}.md`` while ``lib_inventory.py`` decides whether
a declared dependency is documented by normalizing that same file's stem. The
two normalizations live in separate scripts on purpose (the Shared Script
Contract forbids cross-script imports so each stays runnable standalone), which
means nothing but this test stops them from drifting.

Drift is not hypothetical: ``workspace._slugify`` collapses ``.`` to ``-``, so
using it for the library path would file ``ruamel.yaml`` as ``ruamel-yaml.md``
and ``lib_inventory`` would report ``ruamel.yaml`` undocumented forever, with
the doc itself matching no dependency at all.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = REPO_ROOT / ".agents" / "skills" / "_shared" / "workspace.py"
LIB_INVENTORY = (
    REPO_ROOT / ".agents" / "skills" / "update-lib-docs" / "lib_inventory.py"
)


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


workspace = _load_module(WORKSPACE, "workspace_for_slug_agreement")
lib_inventory = _load_module(LIB_INVENTORY, "lib_inventory_for_slug_agreement")

# Every entry is a real-world shape that has broken one of the two sides:
# a dot-bearing distribution, a capitalized name, an underscore name, a PEP 508
# extra, a version specifier, an environment marker, and an npm scope.
PACKAGE_NAMES = [
    "ruamel.yaml",
    "Django",
    "typing_extensions",
    "uvicorn[standard]",
    "ruamel.yaml.clib",
    "zope.interface>=5",
    "backports.zoneinfo; python_version<'3.9'",
    "@types/node",
    "FastAPI",
    "pytest-cov",
]


@pytest.mark.parametrize("raw", PACKAGE_NAMES)
def test_the_two_normalizations_agree(raw: str) -> None:
    assert workspace._package_slug(raw) == lib_inventory.normalize_dep_name(raw)


@pytest.mark.parametrize("raw", PACKAGE_NAMES)
def test_the_agreed_slug_survives_the_cli(raw: str, tmp_path: Path) -> None:
    """The agreement must hold through ``workspace.py``'s CLI, not only its
    helper: the CLI also applies PACKAGE_SLUG_RE, which must accept whatever
    the normalization produces for a real package name."""
    result = subprocess.run(
        [
            sys.executable,
            str(WORKSPACE),
            "--project-root",
            str(tmp_path),
            "--skill",
            "research-lib",
            "--title",
            raw,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["slug"] == lib_inventory.normalize_dep_name(raw)
    assert data["paths"]["lib_doc"] == f".agents/docs/libraries/{data['slug']}.md"


@pytest.mark.parametrize("raw", PACKAGE_NAMES)
def test_a_doc_named_by_workspace_is_seen_as_documented(
    raw: str, tmp_path: Path
) -> None:
    """The end-to-end property that actually matters: a library doc filed at
    the path workspace.py derives is reported as documented — never as an
    undocumented dependency."""
    slug = workspace._package_slug(raw)
    stem = Path(f"{slug}.md").stem
    assert lib_inventory.normalize_dep_name(stem) == lib_inventory.normalize_dep_name(
        raw
    )


def test_dotted_names_are_the_reason_slugify_is_not_reused() -> None:
    """Pin the divergence itself, so the two functions cannot be silently
    merged back into one."""
    assert workspace._slugify("ruamel.yaml") == "ruamel-yaml"
    assert workspace._package_slug("ruamel.yaml") == "ruamel.yaml"
    assert lib_inventory.normalize_dep_name("ruamel.yaml") == "ruamel.yaml"


@pytest.mark.parametrize("raw", PACKAGE_NAMES)
def test_every_agreed_slug_is_a_safe_path_component(raw: str) -> None:
    slug = workspace._package_slug(raw)
    assert workspace.PACKAGE_SLUG_RE.match(slug), f"{raw!r} produced {slug!r}"
    assert "/" not in slug and ".." not in slug
