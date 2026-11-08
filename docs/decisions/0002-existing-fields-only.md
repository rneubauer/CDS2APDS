# 0002. Use only existing fields: `external_references` and `operatorDefinedReference`

Status: accepted (v0.1)

## Context
Links need a place to live in both payloads. New fields would require upstream schema changes.

## Decision
CDS objects carry links in `external_references`; APDS elements carry them in the single-valued
`operatorDefinedReference`. Link kind is derived from the object types, not stored (profile §2.2–2.3).

## Consequences
- APDS can hold only one CDS reference per element; extra links are declared on the CDS side only
  and are valid one-sided links.
- `RightSpecification` has no `operatorDefinedReference`, so permit links are CDS-side only and a
  reverse lookup needs the link service's index.
- Publishers already using `operatorDefinedReference` internally must declare links on the CDS side.
