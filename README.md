## Description

Extracts train ticket prices

## Deployment (Google Cloud Run)

The ntfy watcher runs as a Cloud Run job that Cloud Scheduler starts every 5 minutes, 08:00-23:55 Warsaw time.
At this volume it stays within the free tiers of Cloud Run, Cloud Scheduler, Cloud Build and Artifact Registry.

One-time setup:

1. Create a Google Cloud project and link a billing account (required even when usage is free).
2. Install the [gcloud CLI](https://cloud.google.com/sdk/docs/install) and run `gcloud auth login`.

Deploy, and re-run after every change to redeploy:

```bash
PROJECT_ID=my-project NTFY_TOPIC=my-topic deploy/cloud-run/deploy.sh
```

`REGION` defaults to `europe-west1`. Run once by hand with `gcloud run jobs execute price-watch --region europe-west1`, and see runs under Cloud Run → Jobs → price-watch.
