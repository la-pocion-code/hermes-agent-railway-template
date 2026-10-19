# Hermes Agent Railway Template

## Architecture

There is no application code here. This repository is a thin Railway wrapper
around the official `nousresearch/hermes-agent` image.

- `Dockerfile` — pins the official image by `tag@sha256:digest`, sets the
  `HERMES_*` environment, and installs the compatibility entrypoint
- `docker-entrypoint.sh` — maps the template's legacy `ADMIN_USERNAME` /
  `ADMIN_PASSWORD` variables onto the official `HERMES_DASHBOARD_BASIC_AUTH_*`
  ones, derives a stable session-signing secret, then execs the image's own
  `/opt/hermes/docker/entrypoint-dispatch.sh`. s6-overlay supervises the gateway
  and dashboard from there
- `railway.toml` — Railway build and deploy settings (Dockerfile builder, start
  command, `/api/status` health check)
- `scripts/resolve_hermes_release.py` — resolves which Hermes release to pin
- `.github/workflows/actualizar-hermes.yml` — runs that resolver on a schedule

## Key points

- Hermes state lives in the `/data` volume (`HERMES_HOME=/data/.hermes`), not in
  this repository. Providers, channels, models, skills and profiles are all
  configured through the dashboard
- Never pin `latest` or `stable` in the `Dockerfile` — always a concrete
  `vX.Y.Z` tag plus its digest. The resolver enforces this
- The version pin appears in both `Dockerfile` and `README.md`; change it with
  `scripts/resolve_hermes_release.py --write`, not by hand
- The entrypoint depends on `/opt/hermes/docker/entrypoint-dispatch.sh` existing
  inside the upstream image. If Nous ever moves it, the container stops booting
  and the workflow's smoke test is what catches it
