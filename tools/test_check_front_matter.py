"""Tests for check_front_matter.py. Run: pytest tools/test_check_front_matter.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import check_front_matter as cfm  # noqa: E402

VALID = "---\ntitle: T\naudience: user\nproduct: P\nstatus: current\nreviewed: 2026-11-14\n---\n\n# T\n"


def test_valid_passes():
    assert cfm.check_text(VALID) == []


def test_draft_bool_allowed():
    assert cfm.check_text(VALID.replace("---\n\n#", "draft: true\n---\n\n#")) == []


def test_missing_block():
    assert cfm.check_text("# T\n") == ["no front-matter block at the top of the file"]


def test_bad_audience_and_status():
    text = VALID.replace("audience: user", "audience: staff").replace("status: current", "status: old")
    problems = cfm.check_text(text)
    assert any(p.startswith("audience") for p in problems)
    assert any(p.startswith("status") for p in problems)


def test_reviewed_must_be_date():
    assert any("reviewed" in p for p in cfm.check_text(VALID.replace("2026-11-14", '"2026-11-14"')))
    assert any("reviewed" in p for p in cfm.check_text(VALID.replace("2026-11-14", "soon")))


def test_unknown_key_and_missing_field():
    assert "unknown field: foo" in cfm.check_text(VALID.replace("---\n\n#", "foo: 1\n---\n\n#"))
    assert "missing field: product" in cfm.check_text(VALID.replace("product: P\n", ""))


def test_wrong_types():
    assert any("draft" in p for p in cfm.check_text(VALID.replace("---\n\n#", "draft: yes please\n---\n\n#")))
    assert any("title" in p for p in cfm.check_text(VALID.replace("title: T", "title: 5")))
