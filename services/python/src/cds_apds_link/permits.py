"""T3: shared permit verification (docs/03 §3.4, profile §2.5). Pure functions only."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .jsonutil import as_list
from .registry import RIGHT_SPECS, apds_references

CREDENTIAL_TYPES = ("permit", "licensePlate")
INACTIVE_STATUSES = ("suspended", "planned")
ISO_INSTANT = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?(?:Z|([+-])(\d{2}):(\d{2}))?$", re.ASCII
)


@dataclass(frozen=True)
class Programme:
    curb_policy_id: str
    right_specification_id: str

    def to_json(self) -> dict[str, str]:
        return {"curb_policy_id": self.curb_policy_id, "right_specification_id": self.right_specification_id}


def parse_instant(value: str) -> datetime:
    """Parse an ISO-8601 instant in the profile's strict form to UTC; naive values are UTC. Raises ValueError.

    The accepted form (ISO_INSTANT) and the rules below are identical in both implementations, so a
    timestamp one service can read, the other can too: the fields must form a real calendar date and
    time (no Feb 30, 24:00 or leap second), the offset is below 24:00 with minutes below 60, the UTC
    instant lies in years 0001-9999, and fractional seconds are truncated to milliseconds.
    """
    match = ISO_INSTANT.match(value.strip())
    if not match:
        raise ValueError("not an ISO-8601 instant")
    year, month, day, hour, minute, second = (int(field or 0) for field in match.groups()[:6])
    millis = int((match[7] or "").ljust(3, "0")[:3])
    off_hours, off_minutes = int(match[9] or 0), int(match[10] or 0)
    if off_minutes > 59:
        raise ValueError("offset minutes out of range")
    offset = timedelta(hours=off_hours, minutes=off_minutes) * (-1 if match[8] == "-" else 1)
    local = datetime(year, month, day, hour, minute, second, millis * 1000, tzinfo=timezone(offset))
    try:
        return local.astimezone(timezone.utc)
    except OverflowError:
        raise ValueError("instant is outside years 0001-9999 in UTC") from None


def format_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_credential(value: str) -> str:
    return value.strip().upper()


def compact_credential(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch not in " -")


def mask_credential(value: str) -> str:
    return "*" * len(value) if len(value) <= 6 else f"{value[:3]}***{value[-3:]}"


def _is_permit_rule(rule: Any) -> bool:
    if not isinstance(rule, dict):
        return False
    # Non-arrays count as empty: "permit" in "permit_holder" would otherwise be a substring match.
    return "permit" in as_list(rule.get("user_classes")) or "permit" in as_list(rule.get("purposes"))


def programmes(policies: list[dict[str, Any]]) -> list[Programme]:
    found = set()
    for policy in policies:
        policy_id = policy.get("curb_policy_id")
        rules = policy.get("rules")
        if not isinstance(policy_id, str) or not isinstance(rules, list) or not any(_is_permit_rule(r) for r in rules):
            continue
        for collection, spec_id in apds_references(policy):
            if collection == RIGHT_SPECS:
                found.add(Programme(policy_id, spec_id))
    return sorted(found, key=lambda p: (p.right_specification_id, p.curb_policy_id))


def holds_credential(right: dict[str, Any], credential: str) -> bool:
    holder = right.get("rightHolder")
    creds = holder.get("credentials") if isinstance(holder, dict) else None
    wanted = compact_credential(credential)
    for cred in creds if isinstance(creds, list) else []:
        ident = cred.get("identifier") if isinstance(cred, dict) else None
        if isinstance(ident, dict) and isinstance(ident.get("id"), str) and compact_credential(ident["id"]) == wanted:
            return True
    return False


def _optional_instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return parse_instant(value)
    except ValueError:
        return None


def _bound(record: dict[str, Any], key: str) -> tuple[bool, datetime | None]:
    """(present, instant). A present value that does not parse yields (True, None) so checks fail closed."""
    value = record.get(key)
    return (False, None) if value is None else (True, _optional_instant(value))


def programme_active(spec: dict[str, Any] | None, at: datetime) -> bool:
    if not isinstance(spec, dict):
        return False
    validity = spec.get("validity")
    if not isinstance(validity, dict):
        return False
    # A non-string status counts as absent (profile §2.5: only "suspended" and "planned" are inactive).
    status = validity.get("validityStatus")
    if isinstance(status, str) and status in INACTIVE_STATUSES:
        return False
    period = validity.get("validityTimeSpecification")
    if not isinstance(period, dict):
        return False
    start = _optional_instant(period.get("overallStartTime"))
    has_end, end = _bound(period, "overallEndTime")
    if start is None or start > at:
        return False
    return not has_end or (end is not None and at < end)


def evaluate(right: dict[str, Any], spec: dict[str, Any] | None, at: datetime) -> str:
    has_issued, issued = _bound(right, "issuanceTime")
    has_expiry, expiry = _bound(right, "expiry")
    if has_issued and (issued is None or issued > at):
        return "not_yet_valid"
    if has_expiry and (expiry is None or expiry <= at):
        return "expired"
    if not programme_active(spec, at):
        return "programme_inactive"
    return "valid"


def _latest_first(right: dict[str, Any]) -> tuple[bool, float, str]:
    expiry = _optional_instant(right.get("expiry"))
    # A right without an expiry sorts as having the latest possible expiry; a missing or non-string id as "".
    right_id = right.get("id")
    return (expiry is not None, -expiry.timestamp() if expiry else 0.0, right_id if isinstance(right_id, str) else "")


def decide(outcomes: list[tuple[dict[str, Any], str]]) -> tuple[str, dict[str, Any] | None]:
    """Pick the overall result and the deciding AssignedRight (docs/03 §3.4 step 6)."""
    if not outcomes:
        return "not_found", None
    valid = [right for right, outcome in outcomes if outcome == "valid"]
    if valid:
        return "valid", min(valid, key=_latest_first)
    right, outcome = min(outcomes, key=lambda pair: _latest_first(pair[0]))
    return outcome, right


def right_summary(right: dict[str, Any] | None) -> dict[str, Any] | None:
    if right is None:
        return None
    return {"id": right.get("id"), "version": right.get("version"), "expiry": right.get("expiry")}
