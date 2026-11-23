## Description

Extracts train ticket prices

## Configuration

The ntfy watch (`python -m train_ticket_prices.ntfy_watch`) reads its settings from environment variables. All three
topic variables are required; the program fails at startup if any is missing:

| Variable | Purpose |
| --- | --- |
| `SERVICE__CONFIG__READER__TOPIC` | Ntfy topic to read alert lines from. Each line is `origin->destination;start->end;threshold`, for example `warszawa-centralna->krakow-glowny;2026-11-23T06:00->2026-11-23T12:00;50`. The newest message containing `;` is used. |
| `SERVICE__HISTORY__TOPIC` | Ntfy topic whose recent messages list drops already sent. Read in a 12-hour window. |
| `SERVICE__NOTIFIER_FACTORY__NOTIFIER__TOPIC` | Ntfy topic that new drops are posted to. |

The three can point to the same topic, which is what the workflow does with the `NTFY_TOPIC` secret. Use a separate
topic for notifications if you want the config topic to hold only alert lines.

Optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOGGING_LEVEL` | `20` (INFO) | Python logging level number, for example `10` for DEBUG. |

To run one check locally:

```sh
SERVICE__CONFIG__READER__TOPIC=my-config-topic \
SERVICE__HISTORY__TOPIC=my-topic \
SERVICE__NOTIFIER_FACTORY__NOTIFIER__TOPIC=my-topic \
uv run python -m train_ticket_prices.ntfy_watch
```

## Scheduling

The `price-watch` GitHub workflow does the checking. GitHub's cron is best-effort and often never fires, so the workflow
has no `schedule` trigger. Instead, Google Cloud Scheduler dispatches it every 5 minutes, 08:00-23:55 Warsaw time.
Both stay within their free tiers. The workflow needs the `NTFY_TOPIC` repository secret.

Ntfy is called from GitHub, not from Google Cloud: ntfy.sh rate-limits free use per IP, and Google Cloud's
outgoing IPs are shared and already over that limit.

Setup, from Google Cloud Shell or anywhere `gcloud` is logged in to a project with billing linked:

1. Create a fine-grained GitHub token for this repository with **Actions: Read and write**.
2. Run `PROJECT_ID=my-project GITHUB_TOKEN=github_pat_... deploy/scheduler.sh`. Re-run it when the token expires.

Trigger a run now with `gcloud scheduler jobs run price-watch-github --location europe-west1`.
