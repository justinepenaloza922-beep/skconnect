#!/usr/bin/env bash
# Simple script to run Celery worker + beat for scheduled announcements
# Usage: CELERY_BROKER_URL=redis://localhost:6379/0 SUPABASE_URL=... SUPABASE_KEY=... TWILIO_ACCOUNT_SID=... TWILIO_AUTH_TOKEN=... TWILIO_FROM_NUMBER=... VAPID_PUBLIC_KEY=... VAPID_PRIVATE_KEY=... SMTP_HOST=... SMTP_USER=... SMTP_PASS=... ./scripts/run_celery.sh

set -e

export CELERY_BROKER_URL=${CELERY_BROKER_URL:-redis://localhost:6379/0}
export CELERY_RESULT_BACKEND=${CELERY_RESULT_BACKEND:-$CELERY_BROKER_URL}

# Run celery worker with beat embedded
celery -A celery_worker.celery_app worker --beat --loglevel=info
