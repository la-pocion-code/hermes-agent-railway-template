# Hermes Agent Railway Template

Deploy [Hermes Agent](https://github.com/NousResearch/hermes-agent) on Railway using the official Nous Research image, dashboard, and s6 process supervision. A minimal compatibility entrypoint maps variables from existing template deployments before handing control to the upstream `/init` process.

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/hermes-agent)

## Railway configuration

The Dockerfile is pinned to this official image:

```text
nousresearch/hermes-agent:v0.22.3@sha256:2f305c9bdc81731f48664586d23cb6a6f838a15ad7be1bfabe0c3c269d8e09b9
```

That pin is written by automation — see [Upgrading Hermes](#upgrading-hermes). The compatibility entrypoint delegates to the release's upstream entrypoint dispatcher so both normal PID-1 startup and Railway runtimes with an init wrapper are supported.

Use these service settings:

| Setting | Value |
|---|---|
| Start command | `/usr/local/bin/hermes-railway-entrypoint gateway run` |
| Volume mount | `/data` |
| Public port | `8080` |
| Health-check path | `/api/status` |
| Replicas | `1` |

Railway continues building this GitHub repository so existing template consumers receive update notifications. The compatibility entrypoint only translates legacy environment variables, then executes the official image's `/init`; s6-overlay still supervises the Hermes gateway and dashboard.

### Variables

```dotenv
PORT=8080
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<generated-password>
```

The compatibility entrypoint maps the existing `ADMIN_USERNAME` and sealed `ADMIN_PASSWORD` values to the official dashboard variables before starting `/init`. Existing deployments therefore keep the same login without adding, copying, revealing, or re-entering credentials. It does not modify `config.yaml`. If `ADMIN_PASSWORD` is absent, it generates and logs a password as the previous template did.

For zero-interaction migration, a stable 32-byte dashboard session-signing secret is derived from `ADMIN_PASSWORD`. Derivation supports legacy passwords shorter than Hermes's 16-byte minimum signing-key length while preserving the existing login. After migration, operators may add `HERMES_DASHBOARD_BASIC_AUTH_SECRET` as an independent sealed value containing at least 32 random bytes. Rotating only this secret logs dashboard users out; it does not change the dashboard password or Hermes data. Neither the password nor the derived secret is written to `config.yaml`.

The Dockerfile supplies the remaining official variables:

```dotenv
HERMES_HOME=/data/.hermes
HERMES_WRITE_SAFE_ROOT=/data/.hermes
HERMES_LAZY_INSTALL_TARGET=/data/.hermes/lazy-packages
HERMES_DASHBOARD=1
HERMES_DASHBOARD_HOST=0.0.0.0
HERMES_GATEWAY_BOOTSTRAP_STATE=running
```

The entrypoint maps `PORT` to `HERMES_DASHBOARD_PORT` at runtime.

Provider credentials, messaging channels, models, skills, profiles, and gateway state are managed through the official dashboard and persisted under `/data/.hermes`.

## Upgrading Hermes

This fork keeps itself on the latest Hermes release. The
[`Actualizar Hermes Agent`](.github/workflows/actualizar-hermes.yml) workflow runs
weekdays at 13:00 UTC (08:00 Colombia) and:

1. Reads the `stable` tag of `nousresearch/hermes-agent` on Docker Hub and walks
   its digest back to the matching `vX.Y.Z` tag. Release candidates and the
   `-desktop` image variants can never be selected, and `latest` is never used
   as a pin.
2. Rewrites the pin in `Dockerfile` and in this README to `tag@sha256:digest`,
   so the deployed image stays immutable.
3. **Builds the image and starts the container**, waiting for the gateway to
   answer on `/api/status`. If it does not come up, the job fails and nothing is
   committed — production stays on the version it is already running.
4. Commits to `main`, which Railway picks up and deploys.

So a Hermes release reaches production only after the image has been proven to
build and boot.

### Running it by hand

From the repository's **Actions** tab, `Run workflow` takes two options:

| Option | Use |
|---|---|
| `pin` | Pin a specific release, e.g. `v0.22.1`, instead of following `stable`. This is how you roll back. |
| `dry_run` | Resolve and test the image but commit nothing. |

The same resolver runs locally:

```bash
python scripts/resolve_hermes_release.py --current   # what is live vs. what is available
python scripts/resolve_hermes_release.py --write     # rewrite the pin
```

### Rolling back

Pin the previous release and let the normal flow deploy it:

```bash
python scripts/resolve_hermes_release.py --write --pin v0.22.1
git commit -am "Roll back Hermes Agent to v0.22.1" && git push
```

Rolling back the image does **not** roll back the data in the `/data` volume.
Hermes migrates its state on upgrade, so test a downgrade before relying on it.

### Keeping the schedule alive

GitHub disables scheduled workflows in a repository with no activity for 60
days. The update commits themselves count as activity, so this only matters if
Hermes goes two months without a release — if it does, run the workflow by hand
once to re-arm the schedule.

See the official [Hermes Docker documentation](https://hermes-agent.nousresearch.com/docs/user-guide/docker) for image behavior and configuration details.

## Relationship to the upstream template

This is a fork of [`arjunkomath/hermes-agent-railway-template`](https://github.com/arjunkomath/hermes-agent-railway-template),
which pins releases by hand and can lag months behind Hermes. The automation
above is the reason the fork exists; everything else is kept close to upstream
so their fixes can still be merged in with `gh repo sync` or a pull request.
