#!/usr/bin/env bash
# Build the seed_browser.apworld bundle from the seed_browser/ package.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

dist_dir="$repo_root/dist"
artifact="$dist_dir/seed_browser.apworld"

mkdir -p "$dist_dir"
rm -f "$artifact"

zip -r "$artifact" seed_browser \
    -x 'seed_browser/__pycache__/*' \
       'seed_browser/*/__pycache__/*' \
       '*.pyc' \
    > /dev/null

echo "Built $artifact"
