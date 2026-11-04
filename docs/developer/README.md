# Developer guide

For engineers joining the project. It explains how the repository fits together and how to change it
safely. Read [AGENTS.md](../../AGENTS.md) first: it has the project rules and the checks every PR must pass.

| Page | What it covers |
|---|---|
| [Architecture](architecture.md) | The two standards, the three touchpoints, the link service, and where the profile, services and conformance suite fit |
| [Code map](code-map.md) | Every top-level folder, every module in both services, the conformance file format, `tools/`, `vendor/`, `examples/` |
| [Build, run and test](build-run-test.md) | Commands for both services and the example validator; how to add a conformance case and keep both services in step |
| [Data model](data-model.md) | Link kinds, how links are harvested, issues, and the registry lifecycle |

Related documents:

- [docs/02-link-profile.md](../02-link-profile.md): the normative link profile.
- [docs/03-link-service.md](../03-link-service.md): the contract for the reference link service.
- [docs/decisions/](../decisions/README.md): why things are the way they are.
- [Admin guide](../admin-guide/README.md): installing, configuring and running the service.

These pages describe the code as it is today (v0.1, written 2026-11-03). Draft PRs #3 to #6 are not merged
yet. Where they would change behaviour, the pages say so in a "Pending changes" note.
