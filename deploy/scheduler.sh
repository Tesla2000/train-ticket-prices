#!/usr/bin/env bash
# Creates (or recreates) the Cloud Scheduler job that starts the price-watch GitHub workflow
# every 5 minutes, 08:00-23:55 Warsaw time. GitHub's own cron is best-effort and often never fires.
# Usage: PROJECT_ID=my-project GITHUB_TOKEN=github_pat_... deploy/scheduler.sh
# GITHUB_TOKEN: fine-grained token for this repository with Actions read and write.
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${GITHUB_TOKEN:?set GITHUB_TOKEN}"
REGION="${REGION:-europe-west1}"
JOB="price-watch-github"
REPO="Tesla2000/train-ticket-prices"

gcloud config set project "$PROJECT_ID"
gcloud services enable cloudscheduler.googleapis.com

if gcloud scheduler jobs describe "$JOB" --location "$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs delete "$JOB" --location "$REGION" --quiet
fi
gcloud scheduler jobs create http "$JOB" \
  --location "$REGION" \
  --schedule "*/5 8-23 * * *" \
  --time-zone Europe/Warsaw \
  --http-method POST \
  --uri "https://api.github.com/repos/${REPO}/actions/workflows/price-watch.yml/dispatches" \
  --headers "Authorization=Bearer ${GITHUB_TOKEN},Accept=application/vnd.github+json,Content-Type=application/json,User-Agent=price-watch-scheduler" \
  --message-body '{"ref":"main"}'
