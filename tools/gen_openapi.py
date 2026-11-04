"""Write docs/api/openapi.json from the Python reference service.

The file is generated, never hand-edited. CI regenerates it and fails if the
committed copy differs, so run this after changing any route:

    pip install -e "services/python"
    python tools/gen_openapi.py           # write docs/api/openapi.json
    python tools/gen_openapi.py --check   # exit 1 if the committed file is stale

The app is built with dummy settings and a transport that refuses every call,
so no network access happens. Output is deterministic: sorted keys, two-space
indent, trailing newline.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / "docs" / "api" / "openapi.json"
sys.path.insert(0, str(REPO / "services" / "python" / "src"))

from cds_apds_link import Settings, create_app  # noqa: E402

DUMMY_SETTINGS = Settings(cds_base_url="https://cds.invalid", apds_base_url="https://apds.invalid/v4")


def _no_network(request: httpx.Request) -> httpx.Response:
    raise RuntimeError(f"gen_openapi must not call upstream ({request.url})")


def render() -> str:
    app = create_app(DUMMY_SETTINGS, transport=httpx.MockTransport(_no_network))
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the committed file is out of date")
    args = parser.parse_args()
    text = render()
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT.relative_to(REPO)} is out of date: run python tools/gen_openapi.py", file=sys.stderr)
            return 1
        print(f"{OUTPUT.relative_to(REPO)} is up to date")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
