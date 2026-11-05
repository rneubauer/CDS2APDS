"""Link registry: harvest declarations from both sides and merge them (docs/03 §3.3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .jsonutil import as_list

LINK_KINDS = ("access", "permit", "supply")

CDS_ID_FIELDS = {
    "CurbZone": "curb_zone_id",
    "CurbArea": "curb_area_id",
    "CurbSpace": "curb_space_id",
    "CurbObject": "curb_object_id",
    "CurbPolicy": "curb_policy_id",
}
CLASSNAME_TO_CDS = {"CdsCurbZone": "CurbZone", "CdsCurbArea": "CurbArea", "CdsCurbSpace": "CurbSpace", "CdsCurbObject": "CurbObject"}

PLACES, RIGHT_SPECS = "places", "rights/specs"

# Webhook upserts of new ids are refused beyond this many elements (or right specifications).
MAX_REGISTRY_ENTRIES = 100_000


@dataclass(frozen=True, order=True)
class Ref:
    type: str
    id: str

    def to_json(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id}


@dataclass(frozen=True)
class Link:
    kind: str
    status: str
    cds: Ref
    apds: Ref

    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.kind, self.cds.type, self.cds.id, self.apds.id)

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "status": self.status, "cds": self.cds.to_json(), "apds": self.apds.to_json()}


@dataclass(frozen=True)
class Issue:
    code: str
    cds: Ref | None
    apds: Ref | None
    detail: str

    def sort_key(self) -> tuple[str, str, str, str]:
        return (self.code, self.cds.id if self.cds else "", self.apds.id if self.apds else "", self.detail)

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "cds": self.cds.to_json() if self.cds else None,
            "apds": self.apds.to_json() if self.apds else None,
            "detail": self.detail,
        }


@dataclass
class CdsSnapshot:
    zones: list[dict[str, Any]] = field(default_factory=list)
    areas: list[dict[str, Any]] = field(default_factory=list)
    objects: list[dict[str, Any]] = field(default_factory=list)
    policies: list[dict[str, Any]] = field(default_factory=list)

    def records(self) -> list[tuple[str, dict[str, Any]]]:
        return (
            [("CurbZone", z) for z in self.zones]
            + [("CurbArea", a) for a in self.areas]
            + [("CurbObject", o) for o in self.objects]
            + [("CurbPolicy", p) for p in self.policies]
        )


@dataclass
class ApdsSnapshot:
    elements: dict[str, dict[str, Any]] = field(default_factory=dict)
    right_specs: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_lists(cls, elements: list[dict[str, Any]], right_specs: list[dict[str, Any]]) -> ApdsSnapshot:
        return cls(
            elements={e["id"]: e for e in elements if isinstance(e.get("id"), str)},
            right_specs={s["id"]: s for s in right_specs if isinstance(s.get("id"), str)},
        )


def parse_apds_reference(ref: Any) -> tuple[str, str] | None:
    """Return (collection, id) for an APDS external reference, None if it is not one, or ("", "") if unusable."""
    # Non-string values count as absent. lower(), not casefold(), matches JS toLowerCase ("apdſ" is not APDS).
    name = ref.get("name") if isinstance(ref, dict) else None
    if not isinstance(name, str) or name.lower() != "apds":
        return None
    # Profile §2.2: reference_url MUST be an absolute URL; anything else is unusable.
    path = _http_path(ref.get("reference_url"))
    segments = [s for s in path.split("/") if s]
    ids = ref.get("ids")
    explicit = ids[0] if isinstance(ids, list) and ids and isinstance(ids[0], str) and ids[0] else None
    for i, seg in enumerate(segments):
        if seg == "rights" and i + 1 < len(segments) and segments[i + 1] == "specs":
            tail = segments[i + 2] if i + 2 < len(segments) else None
            return (RIGHT_SPECS, explicit or tail) if (explicit or tail) else ("", "")
        if seg == "places":
            tail = segments[i + 1] if i + 1 < len(segments) else None
            return (PLACES, explicit or tail) if (explicit or tail) else ("", "")
    return ("", "")


def _http_path(raw: Any) -> str:
    """Path of an absolute http(s) URL, or "" if the value is not one (urlparse raises on e.g. "http://[x")."""
    if not isinstance(raw, str):
        return ""
    try:
        url = urlparse(raw)
    except ValueError:
        return ""
    return url.path if url.scheme in ("http", "https") and url.netloc else ""


def _element_type(element: dict[str, Any]) -> str:
    """An element's ``type``; a missing, empty or non-string value counts as "place"."""
    value = element.get("type")
    return value if isinstance(value, str) and value else "place"


def apds_references(record: dict[str, Any]) -> list[tuple[str, str]]:
    refs = as_list(record.get("external_references"))
    return [parsed for parsed in (parse_apds_reference(r) for r in refs) if parsed is not None]


class _Merger:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.issues: set[Issue] = set()

    def add(self, kind: str, cds: Ref, apds: Ref, side: str) -> None:
        key = (cds.type, cds.id, apds.id)
        entry = self.entries.setdefault(key, {"kind": kind, "cds": cds, "apds": apds, "sides": set()})
        entry["sides"].add(side)

    def issue(self, code: str, cds: Ref | None, apds: Ref | None, detail: str) -> None:
        self.issues.add(Issue(code, cds, apds, detail))

    def result(self) -> tuple[list[Link], list[Issue]]:
        links = []
        for e in self.entries.values():
            sides = e["sides"]
            status = "confirmed" if len(sides) == 2 else ("cds_only" if "cds" in sides else "apds_only")
            links.append(Link(e["kind"], status, e["cds"], e["apds"]))
        return sorted(links, key=Link.sort_key), sorted(self.issues, key=Issue.sort_key)


def _cds_side(cds: CdsSnapshot, apds: ApdsSnapshot, merger: _Merger) -> None:
    for cds_type, record in cds.records():
        cds_id = record.get(CDS_ID_FIELDS[cds_type])
        if not isinstance(cds_id, str):
            continue
        cref = Ref(cds_type, cds_id)
        for collection, apds_id in apds_references(record):
            if not collection:
                merger.issue("invalid_reference", cref, None, f"{cds_type} {cds_id} has an APDS reference with an unrecognised URL")
            elif collection == RIGHT_SPECS:
                _cds_permit(cref, apds_id, apds, merger)
            else:
                _cds_place(cref, apds_id, apds, merger)


def _cds_permit(cref: Ref, apds_id: str, apds: ApdsSnapshot, merger: _Merger) -> None:
    aref = Ref("RightSpecification", apds_id)
    if cref.type != "CurbPolicy":
        merger.issue("invalid_reference", cref, aref, f"only a CurbPolicy may reference a RightSpecification, not {cref.type}")
        return
    if apds_id not in apds.right_specs:
        merger.issue("apds_target_missing", cref, aref, f"CurbPolicy {cref.id} references RightSpecification {apds_id}, which does not exist")
    merger.add("permit", cref, aref, "cds")


def _cds_place(cref: Ref, apds_id: str, apds: ApdsSnapshot, merger: _Merger) -> None:
    element = apds.elements.get(apds_id)
    apds_type = _element_type(element) if element else "place"
    aref = Ref(apds_type, apds_id)
    if cref.type == "CurbPolicy":
        merger.issue("invalid_reference", cref, aref, "a CurbPolicy may only reference a RightSpecification")
        return
    if element is None:
        merger.issue("apds_target_missing", cref, aref, f"{cref.type} {cref.id} references APDS element {apds_id}, which does not exist")
    merger.add("access" if apds_type == "vehicularAccess" else "supply", cref, aref, "cds")


def _apds_side(cds: CdsSnapshot, apds: ApdsSnapshot, merger: _Merger) -> None:
    # Only string ids can match a reference; other values may not even be hashable.
    known = {(t, r.get(CDS_ID_FIELDS[t])) for t, r in cds.records() if isinstance(r.get(CDS_ID_FIELDS[t]), str)}
    successor = {
        prev: z["curb_zone_id"]
        for z in cds.zones
        for prev in as_list(z.get("prev_curb_zone_ids"))
        if isinstance(prev, str) and isinstance(z.get("curb_zone_id"), str)
    }
    for element in sorted(apds.elements.values(), key=lambda e: e["id"]):
        ref = element.get("operatorDefinedReference")
        if not isinstance(ref, dict) or not isinstance(ref.get("id"), str):
            continue
        if not isinstance(ref.get("className"), str) or ref["className"] not in CLASSNAME_TO_CDS:
            continue
        apds_type = _element_type(element)
        aref = Ref(apds_type, element["id"])
        cds_type, cds_id = CLASSNAME_TO_CDS[ref["className"]], ref["id"]
        if (cds_type, cds_id) not in known:
            if cds_type == "CurbZone" and cds_id in successor:
                merger.issue("stale_cds_reference", Ref(cds_type, cds_id), aref, f"curb zone {cds_id} was replaced by {successor[cds_id]}")
                cds_id = successor[cds_id]
            else:
                merger.issue("cds_target_missing", Ref(cds_type, cds_id), aref, f"APDS element {element['id']} references {cds_type} {cds_id}, which does not exist")
                continue
        merger.add("access" if apds_type == "vehicularAccess" else "supply", Ref(cds_type, cds_id), aref, "apds")


def build_links(cds: CdsSnapshot, apds: ApdsSnapshot) -> tuple[list[Link], list[Issue]]:
    merger = _Merger()
    _cds_side(cds, apds, merger)
    _apds_side(cds, apds, merger)
    return merger.result()


class Registry:
    """In-memory registry state. All mutation goes through ``_commit`` so links stay consistent."""

    def __init__(self, max_entries: int = MAX_REGISTRY_ENTRIES) -> None:
        self.max_entries = max_entries
        self.cds = CdsSnapshot()
        self.apds = ApdsSnapshot()
        self.links: list[Link] = []
        self.issues: list[Issue] = []
        self.last_sync: str | None = None

    @property
    def synced(self) -> bool:
        return self.last_sync is not None

    def replace(self, cds: CdsSnapshot, apds: ApdsSnapshot, synced_at: str) -> None:
        self._commit(cds, apds, synced_at)

    def upsert_element(self, element: dict[str, Any]) -> bool:
        """Insert or replace an element. Returns False (and changes nothing) if a new id would exceed the cap."""
        if element["id"] not in self.apds.elements and len(self.apds.elements) >= self.max_entries:
            return False
        self._commit(self.cds, ApdsSnapshot({**self.apds.elements, element["id"]: element}, self.apds.right_specs))
        return True

    def remove_element(self, element_id: str) -> None:
        self._commit(self.cds, ApdsSnapshot({k: v for k, v in self.apds.elements.items() if k != element_id}, self.apds.right_specs))

    def upsert_right_spec(self, spec: dict[str, Any]) -> bool:
        """Insert or replace a RightSpecification. Returns False if a new id would exceed the cap."""
        if spec["id"] not in self.apds.right_specs and len(self.apds.right_specs) >= self.max_entries:
            return False
        self._commit(self.cds, ApdsSnapshot(self.apds.elements, {**self.apds.right_specs, spec["id"]: spec}))
        return True

    def remove_right_spec(self, spec_id: str) -> None:
        self._commit(self.cds, ApdsSnapshot(self.apds.elements, {k: v for k, v in self.apds.right_specs.items() if k != spec_id}))

    def find(self, cds_id: str | None = None, apds_id: str | None = None, kind: str | None = None) -> list[Link]:
        return [
            link
            for link in self.links
            if (cds_id is None or link.cds.id == cds_id)
            and (apds_id is None or link.apds.id == apds_id)
            and (kind is None or link.kind == kind)
        ]

    def _commit(self, cds: CdsSnapshot, apds: ApdsSnapshot, synced_at: str | None = None) -> None:
        """Build links for the new snapshots first, then swap all state in; a failed build changes nothing."""
        links, issues = build_links(cds, apds)
        last_sync = synced_at if synced_at is not None else self.last_sync
        self.cds, self.apds, self.links, self.issues, self.last_sync = cds, apds, links, issues, last_sync
