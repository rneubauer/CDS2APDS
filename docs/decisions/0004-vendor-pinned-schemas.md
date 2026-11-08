# 0004. Vendor pinned upstream schemas; patch upstream bugs in memory only

Status: accepted (v0.1)

## Context
Examples must be validated against the official schemas, but both upstream schema sets contain
bugs that make valid payloads fail (profile §2.9).

## Decision
Keep unmodified copies at pinned commits in `vendor/`. `tools/validate_examples.py` applies the
minimal fixes in memory and prints them on every run.

## Consequences
Validation is reproducible offline and the vendored files stay byte-identical to upstream.
The in-memory patches can be removed once upstream fixes land and `vendor/` is bumped.
