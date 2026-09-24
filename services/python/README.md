# CDS–APDS link service (Python)

Python reference implementation of the [link service](../../docs/03-link-service.md): FastAPI with httpx.
It behaves identically to the [TypeScript implementation](../typescript); both pass the shared
[conformance suite](../../conformance).

## Run

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

export CDS_BASE_URL=https://cds.example.org
export APDS_BASE_URL=https://apds.example.org/v4
export APDS_TOKEN=...            # optional; see docs/03 §3.1 for all variables
python -m cds_apds_link          # or: cds-apds-link
```

## Test

```bash
pytest --cov                     # conformance suite + unit tests
```

## Layout

| Module | Responsibility |
|---|---|
| `config.py` | Environment variables → validated `Settings` |
| `upstream.py` | CDS and APDS HTTP clients (auth, paging, untrusted-response checks) |
| `registry.py` | Harvest `external_references` / `operatorDefinedReference`, merge links, report issues |
| `offstreet.py` | T2 nearby off-street summary |
| `permits.py` | T3 permit programme detection and credential evaluation |
| `geo.py` | Centroid, haversine, rounding |
| `app.py` | HTTP routes, the response envelope and error mapping |
