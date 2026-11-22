## Description

Extracts train ticket prices

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
