#!/usr/bin/env python3
"""Write the release notes for a tag (SENS-9).

An OpenRouter model writes a short summary and sorts the changes into
sections. The script adds the full commit list and the compare link itself,
so nothing is lost if the model leaves something out. If the model call
fails, or its answer can't be used, the notes are just the commit list,
as before, and the release still goes out.

Writes two files to --out-dir, which differ only in the compare link:
forgejo.md and github.md.

Standard library only: it runs straight on the CI runner's python3, which
is Debian trixie's 3.13, not the 3.14 the integration targets. Keep it
3.13-compatible; tests/test_release_notes.py checks.

Environment:
  RELEASE_BOT_OPENROUTER_KEY  OpenRouter API key. Without it the notes are
                              the commit list only.
  RELEASE_NOTES_MODEL         override the model (optional)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
# Same model as homelab's AI PR review (HOME-289 bake-off).
MODEL = "openai/gpt-6.1-sol"
# Pinned to OpenAI's own hosting, and never to providers that store prompts.
PROVIDER = {"order": ["openai"], "allow_fallbacks": False, "data_collection": "deny"}
FORGEJO_REPO_URL = "https://gitea.berry.house/kyleberry/sensorpush_local"
GITHUB_REPO_URL = "https://github.com/kyleberry/sensorpush_local"
# Total time for the model call, retries included.
DEADLINE_SECONDS = 300

# Section key -> heading. The order here is the order in the notes.
SECTIONS = {
    "new": "✨ New & improved",
    "fixes": "🐛 Fixes",
    "compatibility": "🏠 Home Assistant compatibility",
    "maintenance": "🧰 Maintenance",
}

SYSTEM_PROMPT = """\
You write the release notes for SensorPush Local, a Home Assistant custom
integration (installed through HACS) that reads battery voltage from
SensorPush sensors over Bluetooth. The readers are Home Assistant users
deciding whether to update, not developers.

You get the commits in this release (subjects and bodies), the dependency
versions that changed, and the Home Assistant versions involved. Reply with
one JSON object and nothing else:

{
  "summary": "...",
  "sections": {
    "new": ["..."],
    "fixes": ["..."],
    "compatibility": ["..."],
    "maintenance": ["..."]
  }
}

summary: one to three plain sentences on what this release means for a user.
If nothing changes for users (only dependency, CI or tooling work), say so in
one sentence, e.g. "A maintenance release with no changes to how the
integration behaves."

sections, each a list of short bullets (no leading "- "):
- new: new features or behaviour users will notice.
- fixes: bugs fixed, described by the problem users saw.
- compatibility: the Home Assistant version the release was tested against,
  and the minimum Home Assistant version if it changed. Use the versions
  given; don't guess.
- maintenance: dependency updates, CI, release tooling, tests, docs. Keep it
  short: fold all dependency bumps into one or two bullets that name the
  notable packages, and fold related CI or tooling commits together.

Rules:
- Use only what the commits say. Don't invent features, fixes or versions.
- Write for users: say what changed for them, not which function changed.
- Keep PR references like (#32) when a commit has one. Don't add commit
  hashes, ticket keys (SENS-2, HOME-302) or co-author lines.
- Leave a section as an empty list when nothing belongs in it.
- Plain Markdown inside strings is fine (backticks for entity or option
  names); no headings.
"""


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()


def previous_tag(tag: str) -> str | None:
    try:
        return git("describe", "--tags", "--abbrev=0", f"{tag}^")
    except subprocess.CalledProcessError:
        return None


def commit_range(prev: str | None, tag: str) -> str:
    return f"{prev}..{tag}" if prev else tag


def commit_list(prev: str | None, tag: str) -> str:
    """The plain list the release notes used before (SENS-9)."""
    return git("log", "--pretty=format:- %s (%h)", commit_range(prev, tag))


def commits_for_model(prev: str | None, tag: str) -> str:
    """Subjects and bodies, minus co-author trailers."""
    raw = git("log", "--format=%x1e%s%n%b", commit_range(prev, tag))
    out = []
    for entry in raw.split("\x1e"):
        lines = [
            line
            for line in entry.strip().splitlines()
            if not line.lower().startswith("co-authored-by:")
        ]
        if lines:
            out.append("\n".join(lines).strip())
    return "\n\n---\n\n".join(out)


PIN = re.compile(r'^\s*"([A-Za-z0-9_.\-\[\]]+)==([^"]+)"')


def pins(ref: str) -> dict[str, str]:
    """name -> version for every exact pin in pyproject.toml at ref."""
    try:
        text = git("show", f"{ref}:pyproject.toml")
    except subprocess.CalledProcessError:
        return {}
    found = {}
    for line in text.splitlines():
        m = PIN.match(line)
        if m:
            found[re.sub(r"\[.*\]", "", m.group(1))] = m.group(2)
    return found


def min_ha_version(ref: str) -> str | None:
    try:
        return json.loads(git("show", f"{ref}:hacs.json")).get("homeassistant")
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def facts(prev: str | None, tag: str) -> str:
    """Versions worked out here, so the model doesn't have to guess them."""
    new, old = pins(tag), pins(prev) if prev else {}
    lines = [f"Release: {tag}" + (f" (previous: {prev})" if prev else "")]
    if "homeassistant" in new:
        lines.append(f"Tested against Home Assistant {new['homeassistant']}")
    min_new = min_ha_version(tag)
    min_old = min_ha_version(prev) if prev else None
    if min_new:
        changed = f" (was {min_old})" if min_old and min_old != min_new else ""
        lines.append(f"Minimum Home Assistant version: {min_new}{changed}")
    bumps = [
        f"- {name}: {old[name]} -> {ver}" if name in old else f"- {name}: added {ver}"
        for name, ver in sorted(new.items())
        if old.get(name) != ver
    ]
    bumps += [f"- {name}: removed" for name in sorted(old) if name not in new]
    if bumps:
        lines.append("Dependency pins changed in pyproject.toml:")
        lines.extend(bumps)
    return "\n".join(lines)


class HTTPFailure(Exception):
    def __init__(self, code: int, body: str):
        super().__init__(f"HTTP {code}: {body[:300]}")
        self.code = code


def post_json(url: str, key: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # OpenRouter app attribution; hidden keeps it out of public rankings.
            "HTTP-Referer": FORGEJO_REPO_URL,
            "X-OpenRouter-Title": "sensorpush_local Release Bot",
            "X-OpenRouter-App-Visibility": "hidden",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        raise HTTPFailure(e.code, e.read().decode(errors="replace")) from e


def call_model(model: str, prompt: str, key: str) -> str:
    """One chat call with retries; returns the reply text."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 4000,
        "reasoning": {"effort": "low"},
        "response_format": {"type": "json_object"},
        "provider": PROVIDER if model == MODEL else {"data_collection": "deny"},
    }
    deadline = time.monotonic() + DEADLINE_SECONDS
    delay = 10
    for attempt in range(1, 4):
        remaining = int(deadline - time.monotonic())
        if remaining < 30:
            break
        try:
            resp = post_json(OPENROUTER, key, body, timeout=remaining)
            if "error" in resp:
                raise RuntimeError(
                    f"OpenRouter error: {json.dumps(resp['error'])[:300]}"
                )
            return resp["choices"][0]["message"]["content"] or ""
        except HTTPFailure as e:
            if e.code not in (408, 429, 500, 502, 503, 504) or attempt == 3:
                raise RuntimeError(f"OpenRouter {e}") from e
            print(f"OpenRouter HTTP {e.code}; retrying in {delay}s", file=sys.stderr)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                raise RuntimeError(f"OpenRouter unreachable: {e}") from e
            print(f"OpenRouter {e}; retrying in {delay}s", file=sys.stderr)
        time.sleep(min(delay, max(0, deadline - time.monotonic())))
        delay *= 3
    raise RuntimeError(f"gave up after {DEADLINE_SECONDS // 60} minutes")


def render_ai_part(reply: str) -> str:
    """Turn the model's JSON into Markdown; raises ValueError if unusable."""
    reply = reply.strip()
    # Some models wrap JSON in a code fence despite response_format.
    reply = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply)
    try:
        data = json.loads(reply)
    except json.JSONDecodeError as e:
        raise ValueError(f"reply is not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("reply is not a JSON object")
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("reply has no summary")
    sections = data.get("sections")
    if sections is None:
        sections = {}
    if not isinstance(sections, dict):
        raise ValueError("sections is not an object")
    parts = [summary.strip()]
    for key, heading in SECTIONS.items():
        items = sections.get(key) or []
        if not isinstance(items, list):
            raise ValueError(f"section {key} is not a list")
        bullets = [
            "- " + re.sub(r"^[-*]\s+", "", str(i).strip())
            for i in items
            if str(i).strip()
        ]
        if bullets:
            parts.append(f"### {heading}\n\n" + "\n".join(bullets))
    return "\n\n".join(parts)


def notes(ai_part: str | None, commits: str, count: int, compare: str | None) -> str:
    if ai_part is None:
        body = commits
    else:
        body = (
            f"{ai_part}\n\n<details>\n<summary>All commits ({count})</summary>\n\n"
            f"{commits}\n\n</details>"
        )
    if compare:
        body += f"\n\n**Full Changelog**: {compare}"
    return body + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("tag", help="the release tag, e.g. v1.0.7")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--print-prompt", action="store_true", help="print the model input and stop"
    )
    args = parser.parse_args()

    tag = args.tag
    prev = previous_tag(tag)
    commits = commit_list(prev, tag)
    count = len(commits.splitlines())
    prompt = f"{facts(prev, tag)}\n\nCommits, newest first:\n\n{commits_for_model(prev, tag)}"
    if args.print_prompt:
        print(prompt)
        return 0

    ai_part = None
    key = os.environ.get("RELEASE_BOT_OPENROUTER_KEY", "")
    model = os.environ.get("RELEASE_NOTES_MODEL") or MODEL
    if not key:
        print(
            "::warning::RELEASE_BOT_OPENROUTER_KEY not set; using the commit list only"
        )
    else:
        try:
            ai_part = render_ai_part(call_model(model, prompt, key))
            print(f"Release notes written by {model}")
        except (RuntimeError, ValueError, KeyError, IndexError) as e:
            print(
                f"::warning::AI release notes failed, using the commit list only: {e}"
            )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, repo_url in (("forgejo", FORGEJO_REPO_URL), ("github", GITHUB_REPO_URL)):
        compare = f"{repo_url}/compare/{prev}...{tag}" if prev else None
        (args.out_dir / f"{name}.md").write_text(
            notes(ai_part, commits, count, compare)
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
