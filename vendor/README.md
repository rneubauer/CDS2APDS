# Vendored specifications

Pinned, unmodified copies of the two upstream specifications. They are used only to validate
the example payloads and service fixtures in this repository.

| Folder | Source | Commit | License |
|---|---|---|---|
| `apds-4.1/` | https://github.com/parkingdata/spec (`apds-api-4.1.yaml`) | `e10dcfc4cf5e45aaa2f46641a235333fb5585b1b` | MIT, © APDS (Alliance for Parking Data Standards). See `apds-4.1/LICENSE` |
| `cds-1.1/` | https://github.com/openmobilityfoundation/cds-openapi (`APIs/`, `Shared Data Models/`, `Rest Responses/`) | `6f8f4a78b32586f84a67d6ac3a10bf2cfec992a3` | CC BY 4.0, © Open Mobility Foundation. See `cds-1.1/LICENSE` |

The prose specification was read from https://github.com/openmobilityfoundation/curb-data-specification
at commit `04cc74493f9bf9675beb064f64359cef17f4f4a4` (CDS 1.1.0).

To update, replace the folder contents with a newer upstream copy, update the commit hashes above,
and re-run `python tools/validate_examples.py`.
