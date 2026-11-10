"""Tests for scripts/release_notes.py (SENS-9)."""

import ast
import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release_notes.py"
_SPEC = importlib.util.spec_from_file_location("release_notes", _SCRIPT)
release_notes = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release_notes)


def _reply(summary="Fixes a bug.", **sections):
    return json.dumps({"summary": summary, "sections": sections})


def test_render_orders_sections_and_drops_empty():
    """Sections follow SECTIONS order; empty ones are left out."""
    out = release_notes.render_ai_part(
        _reply(
            maintenance=["Dependency updates"],
            fixes=["- Entities no longer vanish (#32)"],
            new=[],
            compatibility=["Tested against Home Assistant 2026.11.1"],
        )
    )
    assert out == (
        "Fixes a bug.\n\n"
        "### 🐛 Fixes\n\n- Entities no longer vanish (#32)\n\n"
        "### 🏠 Home Assistant compatibility\n\n"
        "- Tested against Home Assistant 2026.11.1\n\n"
        "### 🧰 Maintenance\n\n- Dependency updates"
    )


def test_render_accepts_code_fence():
    """A reply wrapped in a ```json fence still parses."""
    out = release_notes.render_ai_part("```json\n" + _reply() + "\n```")
    assert out == "Fixes a bug."


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "[]",
        json.dumps({"sections": {}}),
        _reply(summary="  "),
        json.dumps({"summary": "x", "sections": []}),
        json.dumps({"summary": "x", "sections": {"fixes": "one"}}),
    ],
)
def test_render_rejects_unusable_reply(reply):
    """Anything malformed raises ValueError, which triggers the fallback."""
    with pytest.raises(ValueError):
        release_notes.render_ai_part(reply)


def test_notes_with_ai_part_collapses_commit_list():
    """The commit list goes in a <details> block under the AI part."""
    out = release_notes.notes(
        "Summary.", "- a (1)\n- b (2)", 2, "https://x/compare/v1...v2"
    )
    assert out == (
        "Summary.\n\n<details>\n<summary>All commits (2)</summary>\n\n"
        "- a (1)\n- b (2)\n\n</details>\n\n"
        "**Full Changelog**: https://x/compare/v1...v2\n"
    )


def test_notes_fallback_is_plain_commit_list():
    """Without an AI part the notes are the commit list, as before."""
    assert release_notes.notes(None, "- a (1)", 1, None) == "- a (1)\n"


def test_pin_regex_strips_extras():
    """Pins with extras are keyed by the bare package name."""
    match = release_notes.PIN.match('    "pytest-homeassistant[bluetooth]==2026.11.1",')
    assert match.group(1) == "pytest-homeassistant[bluetooth]"
    assert match.group(2) == "2026.11.1"


def test_script_parses_as_python_3_13():
    """The release job runs the script on the runner's python3 (3.13)."""
    ast.parse(_SCRIPT.read_text(), feature_version=(3, 13))
