# Documentation

This repository is a standards proposal with two reference services, so its docs come in two groups.

**The proposal** (normative; read in order):

| Page | What it is |
|---|---|
| [01-boundary.md](01-boundary.md) | The domain boundary: what overlaps between CDS and APDS, and what deliberately doesn't |
| [02-link-profile.md](02-link-profile.md) | The link profile: the rules every publisher and consumer follows |
| [03-link-service.md](03-link-service.md) | The contract for the optional reference link service |
| [cds-apds-link-profile.html](cds-apds-link-profile.html) | A standalone page of the profile, for sharing |

**Guides** (lab documentation standard):

| Folder | For | What goes in |
|---|---|---|
| [user-guide/](user-guide/README.md) | Data publishers and consumers | How to publish and use links, and the demo walkthrough |
| [admin-guide/](admin-guide/README.md) | People who run the link service | Install, every setting, monitoring, troubleshooting, limits |
| [developer/](developer/README.md) | Engineers working on this repo | Architecture, code map, build and test, data model |
| [api/](api/README.md) | Integrators | The link service API, generated from the Python service, with examples |
| [decisions/](decisions/README.md) | Everyone | Why things are the way they are |

Known gaps, and the plan to close them, are in [docs-backlog.md](docs-backlog.md). What changed in each release is
in [CHANGELOG.md](../CHANGELOG.md). Every change to behaviour, settings, the API
or a screen updates the matching page here in the same PR.
