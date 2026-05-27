#!/usr/bin/env bash
# Build the API image, push it to AWS Lightsail, and deploy it.
# Prereqs: docker, AWS CLI configured, a Lightsail container service created once
# (see docs/deploy/lightsail-runbook.md), and deploy/.env.deploy filled in.
# MUST be run from a checkout that has data/embeddings/ (the corpus is gitignored).
set -euo pipefail

REGION="${AWS_REGION:-eu-west-2}"
SERVICE="${LIGHTSAIL_SERVICE:-proposer-api}"
IMAGE_TAG="proposer-api:latest"
ENV_FILE="${DEPLOY_ENV_FILE:-deploy/.env.deploy}"

[ -f "$ENV_FILE" ] || { echo "ERROR: missing $ENV_FILE (copy from deploy/.env.deploy.example)"; exit 1; }
# shellcheck disable=SC1090
source "$ENV_FILE"

[ -d data/embeddings ] || { echo "ERROR: data/embeddings missing — build from the checkout that has the corpus"; exit 1; }

echo "==> building image ($IMAGE_TAG)"
docker build -t "$IMAGE_TAG" .

echo "==> pushing image to Lightsail service '$SERVICE' ($REGION)"
REF=$(aws lightsail push-container-image --region "$REGION" --service-name "$SERVICE" \
        --label api --image "$IMAGE_TAG" --output json \
      | python3 -c "import sys,json;print(json.load(sys.stdin)['image'])")
echo "    pushed ref: $REF"

echo "==> assembling deployment config"
ENV_JSON=$(python3 - <<'PY'
import json, os
keys = ["APP_ENV","DEBUG","OPENAI_API_KEY","DATABASE_URL","SUPABASE_URL","SUPABASE_KEY",
        "ENABLED_DOMAINS","DEFAULT_DOMAIN","DOMAIN_STRICT_EVAL_GATES",
        "LLM_PREDICTION_PROVIDER","LLM_MEDIATOR_PROVIDER","LLM_INTAKE_PROVIDER",
        "LLM_EXTRACTION_PROVIDER","CORS_ORIGINS"]
print(json.dumps({k: os.environ[k] for k in keys if os.environ.get(k) is not None}))
PY
)
CONTAINERS=$(REF="$REF" ENV_JSON="$ENV_JSON" python3 - <<'PY'
import json, os
print(json.dumps({"api": {"image": os.environ["REF"], "ports": {"8000": "HTTP"},
                          "environment": json.loads(os.environ["ENV_JSON"])}}))
PY
)
ENDPOINT='{"containerName":"api","containerPort":8000,"healthCheck":{"path":"/health","successCodes":"200","intervalSeconds":15,"timeoutSeconds":5,"healthyThreshold":2,"unhealthyThreshold":3}}'

echo "==> creating deployment"
aws lightsail create-container-service-deployment --region "$REGION" --service-name "$SERVICE" \
  --containers "$CONTAINERS" --public-endpoint "$ENDPOINT"

echo "==> done. Watch rollout with:"
echo "    aws lightsail get-container-services --region $REGION --service-name $SERVICE --query 'containerServices[0].{state:state,url:url}'"
