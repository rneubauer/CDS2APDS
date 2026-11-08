# 0003. Two reference services held equal by a shared conformance suite

Status: accepted (v0.1)

## Context
Likely adopters work in different stacks. A single implementation would make the profile look tied to
one language, and behaviour would drift into the code instead of the spec.

## Decision
Ship a Python (FastAPI) and a TypeScript (Fastify) service. Both must pass the language-neutral
`conformance/` cases; behaviour is specified in `docs/03-link-service.md`.

## Consequences
Every behaviour change costs two implementations plus a conformance case. In return, the
conformance suite doubles as an executable spec for third-party implementations.
