"""Fail a pull request that changes behaviour without touching the docs.

    python tools/check_docs_changed.py <base-sha> <head-sha>

Rule (lab documentation standard): a PR that changes service code (services/*/src),
the conformance suite (conformance/) or configuration (.env.example) must also change
something under docs/ or CHANGELOG.md. A PR can opt out with a line in its description
that starts with "Docs: none", followed by the reason, e.g. "Docs: none (refactor only)".

The PR description is read from the GitHub event payload ($GITHUB_EVENT_PATH).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

NEEDS_DOCS = (re.compile(r"^services/[^/]+/src/"), re.compile(r"^conformance/"), re.compile(r"^\.env\.example$"))
COUNTS_AS_DOCS = (re.compile(r"^docs/"), re.compile(r"^CHANGELOG\.md$"))
OPT_OUT = re.compile(r"^\s*Docs:\s*none\b", re.IGNORECASE | re.MULTILINE)


def changed_files(base: str, head: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...{head}"],
                         capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def pr_body() -> str:
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        return ""
    with open(path, encoding="utf-8") as handle:
        event = json.load(handle)
    return (event.get("pull_request") or {}).get("body") or ""


def decide(files: list[str], body: str) -> tuple[bool, str]:
    triggers = [f for f in files if any(p.search(f) for p in NEEDS_DOCS)]
    if not triggers:
        return True, "no service code, conformance or config changes: docs not required"
    if any(p.search(f) for f in files for p in COUNTS_AS_DOCS):
        return True, "code changes come with docs changes"
    if OPT_OUT.search(body):
        return True, "PR description says 'Docs: none'"
    listed = "\n  ".join(triggers)
    return False, (
        f"These files change behaviour or config:\n  {listed}\n"
        "but nothing under docs/ or CHANGELOG.md changed. Update the matching docs in this PR, or add a line\n"
        "'Docs: none (<reason>)' to the PR description."
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    ok, message = decide(changed_files(argv[0], argv[1]), pr_body())
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
