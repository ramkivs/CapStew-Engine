#!/usr/bin/env bash
# Regenerate MANIFEST.sha256 over every tracked file (itself excluded).
#
# Run this after any committed change, before tagging a release. The gate in
# scripts/release_check.sh (R-03b) fails if the manifest is stale or if a
# tracked file is missing from it — so this is the only sanctioned way to
# re-baseline it, and it keeps coverage total rather than partial.
set -euo pipefail
cd "$(dirname "$0")/.."

git ls-files | grep -v '^MANIFEST\.sha256$' | LC_ALL=C sort |
  xargs -d '\n' sha256sum > MANIFEST.sha256

echo "MANIFEST.sha256 regenerated: $(wc -l < MANIFEST.sha256) entries"
sha256sum -c MANIFEST.sha256 >/dev/null && echo "verification: all OK"
