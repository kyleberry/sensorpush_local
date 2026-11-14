"""Tests for scripts/release_notes.py (SENS-9)."""

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


@pytest.mark.parametrize("suffix", ["a1", "b2", "rc3", ""])
def test_previous_tag_skips_betas_for_stable(tmp_path, monkeypatch, suffix):
    """A stable release includes the beta changes; beta notes are incremental."""
    import subprocess  # pylint: disable=import-outside-toplevel

    def run(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    run("init")
    run("config", "user.name", "Test")
    run("config", "user.email", "test@example.com")
    for tag in ["v1.0.8", "v1.0.9b1", f"v1.0.9{suffix}"]:
        run("-c", "commit.gpgsign=false", "commit", "--allow-empty", "-m", tag)
        run("tag", tag)
    monkeypatch.setattr(release_notes, "REPO_ROOT", tmp_path)
    expected = "v1.0.9b1" if suffix else "v1.0.8"
    assert release_notes.previous_tag(f"v1.0.9{suffix}") == expected


def test_prerelease_facts_identify_testing_release(monkeypatch):
    """The model receives an explicit pre-release instruction."""
    monkeypatch.setattr(release_notes, "pins", lambda ref: {})
    monkeypatch.setattr(release_notes, "min_ha_version", lambda ref: None)
    assert "pre-release for opt-in testing" in release_notes.facts(None, "v1.0.9rc1")
    assert "pre-release" not in release_notes.facts(None, "v1.0.9")
