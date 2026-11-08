"""Check that every relative link in the repository's Markdown files resolves.

    python tools/check_links.py            # check all tracked *.md files
    python tools/check_links.py a.md b.md  # check only these files

For each [text](target) or [text]: target link:
- http(s), mailto and other scheme links are skipped (this check is offline);
- a path must exist, relative to the file that links it;
- a #anchor must match a heading in the target Markdown file (GitHub's slug rules),
  or an explicit <a id="..."> / <a name="...">.

Links inside fenced code blocks and inline code are ignored. Exits 1 if anything is broken.
"""
from __future__ import annotations

import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"node_modules", ".git", "vendor", ".venv", "dist", "coverage"}
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`+[^`]*`+")
INLINE_LINK_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
HTML_ANCHOR_RE = re.compile(r"<a\s+[^>]*(?:id|name)=\"([^\"]+)\"", re.IGNORECASE)
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def markdown_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "*.md"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout
        files = [REPO / line for line in out.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        files = list(REPO.rglob("*.md"))
    return sorted(f for f in files if f.is_file() and not SKIP_DIRS.intersection(f.relative_to(REPO).parts))


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Lines outside fenced code blocks, with inline code removed."""
    lines, in_fence = [], False
    for number, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append((number, INLINE_CODE_RE.sub("", line)))
    return lines


def github_slug(heading: str) -> str:
    text = re.sub(r"<[^>]+>", "", heading)                     # drop inline HTML
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)       # links -> their text
    text = text.replace("`", "").strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


@lru_cache(maxsize=None)
def anchors(path: Path) -> frozenset[str]:
    text = path.read_text(encoding="utf-8")
    found, seen = set(HTML_ANCHOR_RE.findall(text)), {}
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else HEADING_RE.match(line)
        if not match:
            continue
        slug = github_slug(match.group(2))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        found.add(slug if count == 0 else f"{slug}-{count}")
    return frozenset(found)


def links_in(text: str) -> list[tuple[int, str]]:
    result = []
    for number, line in prose_lines(text):
        result += [(number, m.group(1)) for m in INLINE_LINK_RE.finditer(line)]
        ref = REF_DEF_RE.match(line)
        if ref:
            result.append((number, ref.group(1)))
    return result


def check_link(source: Path, target: str) -> str | None:
    if SCHEME_RE.match(target) or target.startswith("//"):
        return None
    path_part, _, anchor = target.partition("#")
    path_part = unquote(path_part.split("?", 1)[0])
    if path_part.startswith("/"):
        resolved = (REPO / path_part.lstrip("/")).resolve()
    else:
        resolved = (source.parent / path_part).resolve() if path_part else source
    if not resolved.exists():
        return "file not found"
    if anchor and resolved.is_file() and resolved.suffix.lower() == ".md" and unquote(anchor) not in anchors(resolved):
        return f"no heading for #{anchor}"
    return None


def check(files: list[Path]) -> list[str]:
    problems = []
    for source in files:
        for line, target in links_in(source.read_text(encoding="utf-8")):
            reason = check_link(source, target)
            if reason:
                problems.append(f"{source.relative_to(REPO)}:{line}: {target} ({reason})")
    return problems


def main(argv: list[str]) -> int:
    files = [Path(a).resolve() for a in argv] if argv else markdown_files()
    problems = check(files)
    for problem in problems:
        print(problem)
    print(f"checked {len(files)} Markdown files: {len(problems)} broken link(s)", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
