# CLAUDE.md

Read [AGENTS.md](AGENTS.md) first; it holds the project rules and the checks to run.

Claude-specific notes:

- Work in a branch or worktree and open a PR; do not push to `main`.
- When a change touches service behaviour, update `conformance/cases.json` / `fixtures.json` and both
  `services/python` and `services/typescript` in the same PR, and run all three checks.
- Filing the §2.9 upstream schema issues on GitHub (OMF, APDS) is outward-facing and needs Rick's OK.
