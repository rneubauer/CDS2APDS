# CDS–APDS link service (TypeScript)

TypeScript reference implementation of the [link service](../../docs/03-link-service.md): Fastify on Node 20+,
using the built-in `fetch`. It behaves identically to the [Python implementation](../python); both pass the
shared [conformance suite](../../conformance).

## Run

```bash
npm install
npm run build

export CDS_BASE_URL=https://cds.example.org
export APDS_BASE_URL=https://apds.example.org/v4
export APDS_TOKEN=...            # optional; see docs/03 §3.1 for all variables
npm start
```

## Test

```bash
npm test                         # conformance suite + unit tests
npm run coverage
npm run typecheck
```

## Layout

| Module | Responsibility |
|---|---|
| `config.ts` | Environment variables → validated `Settings` |
| `upstream.ts` | CDS and APDS HTTP clients (auth, paging, timeouts, untrusted-response checks) |
| `registry.ts` | Harvest `external_references` / `operatorDefinedReference`, merge links, report issues |
| `offstreet.ts` | T2 nearby off-street summary |
| `permits.ts` | T3 permit programme detection and credential evaluation |
| `geo.ts` | Centroid, haversine, rounding |
| `service.ts` | Orchestration: registry + live upstream reads |
| `app.ts` | HTTP routes, the response envelope and error mapping |
| `server.ts` | Process entry point |
