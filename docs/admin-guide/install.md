# Install

There are no packages or container images yet. You install from a checkout of the repository.

## Before you start

You need:

1. The base URL of a **CDS 1.1 Curbs API** server, and its bearer token if it needs one.
2. The base URL of an **APDS 4.1 API** server, including the version prefix (for example
   `https://apds.example.org/v4`), and its token if it needs one.
3. A host that can reach both servers over HTTP(S).
4. git, to get the code:
   ```bash
   git clone https://github.com/rneubauer/CDS2APDS.git
   cd CDS2APDS
   ```

Then install **one** of the two versions.

## Option A: Python version

Prerequisites: Python 3.11 or newer with `pip` and `venv`. CI tests 3.11 and 3.13.

1. Create a virtual environment:
   ```bash
   cd services/python
   python -m venv .venv
   . .venv/bin/activate              # Windows: .venv\Scripts\activate
   ```
2. Install the service. This pulls in FastAPI, httpx and uvicorn:
   ```bash
   pip install .
   ```
   Use `pip install -e ".[dev]"` instead if you also want to run the tests.
3. Set the two required variables (see [Configuration](configuration.md) for all of them):
   ```bash
   export CDS_BASE_URL=https://cds.example.org
   export APDS_BASE_URL=https://apds.example.org/v4
   ```
4. Start it:
   ```bash
   cds-apds-link                     # or: python -m cds_apds_link
   ```
5. Check it from another shell:
   ```bash
   curl http://localhost:8080/health
   ```
   Expected: `{"success":true,"data":{"status":"ok","links":0,"last_sync":null},"error":null}`.

## Option B: TypeScript version

Prerequisites: Node.js 20 or newer with npm. CI tests Node 20 and 22.

1. Install dependencies from the lock file and build:
   ```bash
   cd services/typescript
   npm ci
   npm run build                     # writes dist/
   ```
2. Set the two required variables:
   ```bash
   export CDS_BASE_URL=https://cds.example.org
   export APDS_BASE_URL=https://apds.example.org/v4
   ```
3. Start it:
   ```bash
   npm start                         # runs node dist/server.js
   ```
4. Check it:
   ```bash
   curl http://localhost:8080/health
   ```

## If it does not start

The service checks its settings first. If one is wrong it prints `configuration error: <reason>` to stderr
and exits with code **2**. See [Troubleshooting](troubleshooting.md#the-service-exits-at-start).

## Optional: verify the install

Run the test suites to confirm the checkout works on this host (they use built-in fake upstreams and need no
network):

```bash
cd services/python && pip install -e ".[dev]" && pytest
cd services/typescript && npm test
```
