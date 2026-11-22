#!/usr/bin/env bash
# Deploys the price watcher as a Cloud Run job that Cloud Scheduler starts every 5 minutes, 08:00-23:55 Warsaw time.
# Safe to re-run: it updates the job and the schedule in place.
# Usage: PROJECT_ID=my-project NTFY_TOPIC=my-topic deploy/cloud-run/deploy.sh
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
: "${NTFY_TOPIC:?set NTFY_TOPIC}"
REGION="${REGION:-europe-west1}"
JOB="price-watch"
SERVICE_ACCOUNT="${JOB}@${PROJECT_ID}.iam.gserviceaccount.com"
TOPIC_ENV="WATCH__CONFIG__TOPIC=${NTFY_TOPIC},WATCH__HISTORY__TOPIC=${NTFY_TOPIC},WATCH__NOTIFIER__TOPIC=${NTFY_TOPIC}"

cd "$(dirname "$0")/../.."

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$JOB" --display-name="$JOB"
fi

gcloud run jobs deploy "$JOB" \
  --source . \
  --region "$REGION" \
  --service-account "$SERVICE_ACCOUNT" \
  --set-env-vars "$TOPIC_ENV" \
  --max-retries 0 \
  --task-timeout 5m \
  --cpu 1 \
  --memory 512Mi

gcloud run jobs add-iam-policy-binding "$JOB" \
  --region "$REGION" \
  --member "serviceAccount:${SERVICE_ACCOUNT}" \
  --role roles/run.invoker

if gcloud scheduler jobs describe "$JOB" --location "$REGION" >/dev/null 2>&1; then
  SCHEDULER_ACTION=update
else
  SCHEDULER_ACTION=create
fi
gcloud scheduler jobs "$SCHEDULER_ACTION" http "$JOB" \
  --location "$REGION" \
  --schedule "*/5 8-23 * * *" \
  --time-zone Europe/Warsaw \
  --http-method POST \
  --uri "https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${JOB}:run" \
  --oauth-service-account-email "$SERVICE_ACCOUNT"
