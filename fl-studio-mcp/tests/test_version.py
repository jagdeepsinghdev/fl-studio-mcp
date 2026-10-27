"""One version, everywhere: pyproject, the package, and the changelog's newest entry."""
import json
import re
from pathlib import Path

import fl_studio_mcp

ROOT = Path(__file__).resolve().parents[2]


def _pyproject_version() -> str:
    text = (ROOT / "fl-studio-mcp" / "pyproject.toml").read_text()
    return re.search(r'^version = "([^"]+)"', text, re.M).group(1)


def test_package_matches_pyproject():
    assert fl_studio_mcp.__version__ == _pyproject_version()


def test_changelog_lists_this_version():
    log = (ROOT / "CHANGELOG.md").read_text()
    versions = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", log, re.M)
    assert versions and versions[0] == _pyproject_version(), (
        f"CHANGELOG.md newest entry {versions[:1]} != pyproject {_pyproject_version()}")


def test_registry_metadata_matches_the_package():
    """server.json (MCP Registry) must name this package and version, and the PyPI README
    must carry the matching mcp-name line the registry checks."""
    sj = json.loads((ROOT / "server.json").read_text())
    v = _pyproject_version()
    assert sj["version"] == v
    pkg = sj["packages"][0]
    assert pkg["registryType"] == "pypi" and pkg["identifier"] == "fl-studio-mcp" and pkg["version"] == v
    assert len(sj["description"]) <= 100
    readme = (ROOT / "fl-studio-mcp" / "README.md").read_text()
    assert f"mcp-name: {sj['name']}" in readme
