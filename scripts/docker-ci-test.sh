#!/usr/bin/env bash
# Test a built Sunny Narrator image: Calibre and pandoc are there, and the
# whole test suite passes inside it. Used by .gitlab-ci.yml and
# .github/workflows/docker-publish.yml.
#
# Usage: scripts/docker-ci-test.sh IMAGE [JUNIT_REPORT]
#
# The checkout is copied over /app with `docker cp`, not bind-mounted: with a
# docker:dind service a bind mount would resolve inside the dind container,
# where the checkout does not exist. The code is the same commit; the
# environment (Python packages, spaCy models, Calibre, pandoc) is the image's.
# No LLM calls are made (dummy keys, all traffic is mocked in the tests).
set -euo pipefail

image="$1"
report="${2:-}"

echo "== Calibre and pandoc in $image"
docker run --rm --entrypoint ebook-convert "$image" --version
docker run --rm --entrypoint pandoc "$image" --version

echo "== Test suite in $image"
cid=$(docker create --entrypoint bash \
    -e API_KEY_TRANSLATE=ci-dummy-key \
    -e API_KEY_PROOFREAD=ci-dummy-key \
    -e API_KEY_IMAGES=ci-dummy-key \
    "$image" -o pipefail -c '
        python3 -m pip install -q pytest pytest-timeout &&
        python3 -m pytest tests/ -q -rs -p no:cacheprovider --junitxml=/tmp/report.xml | tee /tmp/pytest.log &&
        # in the image the EPUB conversion test must run, not be skipped
        if grep -q "calibre not installed" /tmp/pytest.log; then
            echo "Calibre tests were skipped inside the image"; exit 1;
        fi')
trap 'docker rm -f "$cid" >/dev/null' EXIT
tar -c --exclude=./.git --exclude=./.venv --exclude=./.pip-cache --exclude='__pycache__' . \
    | docker cp - "$cid:/app"

status=0
docker start -a "$cid" || status=$?
if [ -n "$report" ]; then
    docker cp "$cid:/tmp/report.xml" "$report" || true
fi
exit "$status"
