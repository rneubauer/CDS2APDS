# Hosting the demo on the lab tailnet

A runbook for showing the Civic District demo to an audience on the lab tailnet. For what the demo shows, see
the demo user guide (`docs/user-guide/demo.md`, added by PR #7).

## 1. Prerequisites

- Python 3.11 or newer, and a virtual environment.
- The demo is **not on `main` yet.** It needs draft PR #7 merged, or a checkout of the branch
  `feat/civic-district-demo`. Without one of those, `demo/server.py` does not exist.
- From the repository root:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e services/python
```

## 2. Start it and share it

1. Start the server so it survives closing the terminal (it binds to 127.0.0.1 only):

   ```bash
   nohup python demo/server.py --port 8742 > demo.log 2>&1 &
   ```

2. Check it. You should get a JSON health reply:

   ```bash
   curl http://127.0.0.1:8742/health
   ```

3. Share it on the tailnet. Pick a free port from 8100 to 8999 (here 8742 is the local port; the tailnet port can be the same or different):

   ```bash
   tailscale serve --bg --https=<port> http://localhost:8742
   ```

4. Give the audience the link: `https://<host>.<tailnet>.ts.net:<port>/demo/`

## 3. Before the demo

- [ ] Open `/demo/#t1`, `/demo/#t2` and `/demo/#t3` and check each panel fills in.
- [ ] The sample permit `ZA-004217` expires `2026-12-31T23:59:59Z`. After that date, set "Check at" to `2026-06-01T12:00:00Z`.
- [ ] After using the "Feb 2027" chip, reset the date to the default.
- [ ] Present from a laptop. The page works on a phone, but the map is small there.

## 4. Turn it off afterwards

1. `tailscale serve --https=<port> off`
2. Stop the process: `pkill -f demo/server.py`
3. Public links (Tailscale Funnel) for people outside the lab need Rick's OK each time.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| Server exits, `address already in use` (see `demo.log`) | Another process has the port. Pick another with `--port`, or stop the old demo with `pkill -f demo/server.py`. Update the `tailscale serve` target to match. |
| Page loads but panels show errors | The server did not sync, or the page is talking to the wrong port. Check `demo.log`, run the `/health` check, then reload. Restart the server if needed. |
| Tailnet URL does not open | Run `tailscale serve status` to see that the port is listed and points at the right local port. Check that the viewer is on the tailnet. Use `https://`, with the port and the trailing `/demo/`. |
