#!/bin/bash
# End-to-end test of the content-deployer container on this machine.
#
# Builds the image, runs it under the Lambda Runtime Interface Emulator,
# serves a fixture zip over HTTP, sends Create / Update / Delete events the
# way CloudFormation would, and checks what lands in a throwaway S3 bucket.
#
# Requires: docker, aws cli with credentials (AWS_PROFILE), python3.
# Usage: AWS_PROFILE=<profile> tests/docker/run-local.sh [fixture-name ...]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FIXTURES=("$@")
[ "${#FIXTURES[@]}" -eq 0 ] && FIXTURES=(vite-spa vite-spa-bun prebuilt-static)
LAST_FIXTURE="${FIXTURES[$((${#FIXTURES[@]} - 1))]}"
HTTP_PID=""
SINK_PID=""
AWS_PROFILE="${AWS_PROFILE:-default}"
AWS_REGION="${AWS_REGION:-us-east-1}"
IMAGE="prodify-content-deployer:local"
WORK="$(mktemp -d)"
BUCKET="prodify-deployer-test-$(date +%s)"
PORT_HTTP=8765
PORT_RIE=9000

cleanup() {
  docker rm -f prodify-deployer-test >/dev/null 2>&1 || true
  [ -n "$HTTP_PID" ] && kill "$HTTP_PID" >/dev/null 2>&1 || true
  [ -n "$SINK_PID" ] && kill "$SINK_PID" >/dev/null 2>&1 || true
  aws s3 rb "s3://${BUCKET}" --force --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

echo "== Building image"
docker buildx build --platform linux/arm64 --load -t "$IMAGE" "$REPO_ROOT/backend/docker/content-deployer" >/dev/null

echo "== Preparing fixtures in $WORK"
for f in "${FIXTURES[@]}"; do
  (cd "$REPO_ROOT/tests/fixtures" && zip -qr "$WORK/$f.zip" "$f")
done
(cd "$WORK" && exec python3 -m http.server "$PORT_HTTP" >/dev/null 2>&1) &
HTTP_PID=$!

# Captures the PUT CloudFormation would receive.
cat > "$WORK/sink.py" <<'EOF'
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_PUT(self):
        body = self.rfile.read(int(self.headers.get('content-length', 0)))
        with open(sys.argv[1], 'ab') as f:
            f.write(body + b"\n")
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
HTTPServer(('0.0.0.0', 8766), H).serve_forever()
EOF
python3 "$WORK/sink.py" "$WORK/responses.jsonl" &
SINK_PID=$!

echo "== Creating test bucket $BUCKET"
aws s3 mb "s3://${BUCKET}" --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null

echo "== Starting container"
eval "$(aws configure export-credentials --profile "$AWS_PROFILE" --format env)"
docker run -d --rm --name prodify-deployer-test -p "${PORT_RIE}:8080" \
  -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_SESSION_TOKEN -e AWS_REGION="$AWS_REGION" \
  "$IMAGE" >/dev/null
sleep 2

invoke() { # request_type fixture
  local n; n=$(date +%s%N)
  local payload
  payload=$(python3 - "$1" "$2" "$BUCKET" "$n" <<'EOF'
import json, sys
rt, fixture, bucket, n = sys.argv[1:]
print(json.dumps({
  "RequestType": rt,
  "ResponseURL": "http://host.docker.internal:8766/response",
  "StackId": "arn:aws:cloudformation:us-east-1:123456789012:stack/test/1",
  "RequestId": n,
  "LogicalResourceId": "DeploymentTrigger",
  "ResourceProperties": {
    "SourceZipUrl": f"http://host.docker.internal:8765/{fixture}.zip",
    "BucketName": bucket
  }
}))
EOF
)
  : > "$WORK/responses.jsonl"
  echo "-- $1 ($2)"
  curl -s -m 890 -X POST "http://localhost:${PORT_RIE}/2015-03-31/functions/function/invocations" -d "$payload" >/dev/null
  local status; status=$(python3 -c "import json,sys; print(json.load(open('$WORK/responses.jsonl'))['Status'])")
  local reason; reason=$(python3 -c "import json,sys; print(json.load(open('$WORK/responses.jsonl')).get('Reason',''))")
  echo "   -> $status ${reason:+($reason)}"
  [ "$status" = "SUCCESS" ] || { docker logs prodify-deployer-test | tail -40; return 1; }
}

for f in "${FIXTURES[@]}"; do
  invoke Create "$f"
  echo "   bucket contents:"; aws s3 ls "s3://${BUCKET}" --recursive --profile "$AWS_PROFILE" | awk '{print "     " $4}'
  aws s3api head-object --bucket "$BUCKET" --key index.html --profile "$AWS_PROFILE" --query '[ContentType,CacheControl]' --output text | sed 's/^/   index.html: /'
done

echo "-- Update with unchanged source (expect no-op)"
invoke Update "$LAST_FIXTURE"
invoke Delete "$LAST_FIXTURE"
remaining=$(aws s3 ls "s3://${BUCKET}" --recursive --profile "$AWS_PROFILE" | wc -l | tr -d ' ')
echo "   objects after Delete: $remaining"
[ "$remaining" = "0" ] || exit 1

echo
echo "ALL DEPLOYER SCENARIOS PASSED"
