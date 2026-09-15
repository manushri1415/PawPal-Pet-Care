#!/usr/bin/env bash
# Upload the built SPA to the frontend bucket and refresh CloudFront.
#
#   scripts/deploy_frontend.sh <bucket> <distribution-id> [dist-dir]
#
# Caching is decided per object here, at upload, and CloudFront's cache policy
# honours it (infra/template.yaml, StaticCachePolicy):
#   assets/*   content-hashed file names -> cached for a year, immutable
#   the rest   index.html and the un-hashed public/ files -> no-cache, so a
#              deploy is picked up on the next page load
# Old hashed bundles are kept (no --delete under assets/): a tab still running
# the previous index.html can go on loading its chunks after the deploy.
set -euo pipefail

bucket="${1:?usage: deploy_frontend.sh <bucket> <distribution-id> [dist-dir]}"
distribution="${2:?usage: deploy_frontend.sh <bucket> <distribution-id> [dist-dir]}"
dist="${3:-frontend/dist}"

test -f "$dist/index.html" || { echo "no build at $dist (run npm run build)" >&2; exit 1; }

if [ -d "$dist/assets" ]; then
  aws s3 sync "$dist/assets" "s3://$bucket/assets" \
    --cache-control "public, max-age=31536000, immutable" --only-show-errors
fi

aws s3 sync "$dist" "s3://$bucket" \
  --exclude "assets/*" --cache-control "no-cache" --delete --only-show-errors

# One wildcard path per deploy (the first 1,000 paths a month are free).
aws cloudfront create-invalidation --distribution-id "$distribution" --paths "/*" \
  --query "Invalidation.Id" --output text
