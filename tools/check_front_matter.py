"""Check that every docs/**/*.md has valid front matter (lab documentation standard).

    python tools/check_front_matter.py            # check all docs/**/*.md
    python tools/check_front_matter.py a.md b.md  # check only these files

Required: title (non-empty str), audience (user|admin|developer|api|staff), product (non-empty str),
status (current|planned|superseded), reviewed (YYYY-MM-DD date). Optional: draft (bool), source (non-empty str,
where a planning doc came from). Unknown keys are errors.
Prints file:problem lines and exits 1 if anything is wrong. Offline; needs pyyaml.
"""
from __future__ import annotations

import datetime
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
AUDIENCES = {"user", "admin", "developer", "api", "staff"}
STATUSES = {"current", "planned", "superseded"}
KNOWN = {"title", "audience", "product", "status", "reviewed", "draft", "source"}
BLOCK_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_text(text: str) -> list[str]:
    """Problems with one file's front matter (empty list when valid)."""
    match = BLOCK_RE.match(text)
    if not match:
        return ["no front-matter block at the top of the file"]
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as err:
        return [f"front matter is not valid YAML: {err}"]
    if not isinstance(data, dict):
        return ["front matter must be a mapping of keys to values"]
    problems = []
    for key in ("title", "product"):
        if key not in data:
            problems.append(f"missing field: {key}")
        elif not _non_empty_str(data[key]):
            problems.append(f"{key} must be a non-empty string")
    for key, allowed in (("audience", AUDIENCES), ("status", STATUSES)):
        if key not in data:
            problems.append(f"missing field: {key}")
        elif not isinstance(data[key], str) or data[key] not in allowed:
            problems.append(f"{key} must be one of {sorted(allowed)}, got {data[key]!r}")
    if "reviewed" not in data:
        problems.append("missing field: reviewed")
    elif not (isinstance(data["reviewed"], datetime.date) and not isinstance(data["reviewed"], datetime.datetime)):
        problems.append(f"reviewed must be a YYYY-MM-DD date, got {data['reviewed']!r}")
    if "draft" in data and not isinstance(data["draft"], bool):
        problems.append(f"draft must be true or false, got {data['draft']!r}")
    if "source" in data and not _non_empty_str(data["source"]):
        problems.append("source must be a non-empty string")
    problems.extend(f"unknown field: {key}" for key in data if key not in KNOWN)
    return problems


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] or sorted((REPO / "docs").rglob("*.md"))
    failures = 0
    for path in files:
        for problem in check_text(path.read_text(encoding="utf-8")):
            print(f"{path}: {problem}")
            failures += 1
    if failures:
        print(f"{failures} front-matter problem(s)", file=sys.stderr)
        return 1
    print(f"front matter OK in {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
