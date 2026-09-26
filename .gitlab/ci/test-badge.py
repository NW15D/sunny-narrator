#!/usr/bin/env python3
"""Publish/refresh the "N solved / M failed" custom project badge from junit.

Auth: CI/CD variable BADGE_TOKEN = project access token (api scope, reporter).
CI_JOB_TOKEN cannot access the badges API, hence the explicit token.
Runs on main even when the tests job fails (report.xml is uploaded with
when: always), so the badge flips red instead of going stale.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

REPORT = "report.xml"
NAME = "tests-badge"

token = os.environ.get("BADGE_TOKEN", "")
api = f"{os.environ['CI_API_V4_URL']}/projects/{os.environ['CI_PROJECT_ID']}/badges"
project_url = os.environ.get("CI_PROJECT_URL", "")
ref = os.environ.get("CI_COMMIT_REF_NAME", "main")


def req(url, data=None, method=None):
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("PRIVATE-TOKEN", token)
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main():
    if not token:
        print("BADGE_TOKEN not set - skipping badge publish")
        return 0
    if not os.path.exists(REPORT):
        print(f"No {REPORT} - skipping badge update")
        return 0

    suite = ET.parse(REPORT).getroot()
    if suite.tag != "testsuite":  # some writers nest under <testsuites>
        suite = suite.find("testsuite")
    tests = int(suite.get("tests", 0))
    failures = int(suite.get("failures", 0))
    errors = int(suite.get("errors", 0))
    skipped = int(suite.get("skipped", 0))
    bad = failures + errors
    passed = tests - bad - skipped
    color = "brightgreen" if bad == 0 else "red"
    label = "tests"
    value = f"{passed} solved / {bad} failed"

    shields = f"https://img.shields.io/badge/{urllib.parse.quote(label)}-{urllib.parse.quote(value)}-{color}"
    image_url = shields + ".svg"
    link_url = f"{project_url}/-/jobs/artifacts/{ref}/raw/report.xml?job=tests"

    existing = None
    for b in req(f"{api}?per_page=100"):
        if b.get("name") == NAME:
            existing = b["id"]
            break

    body = urllib.parse.urlencode({"link_url": link_url, "image_url": image_url}).encode()
    if existing:
        req(f"{api}/{existing}", data=body, method="PUT")
        print(f"Badge {existing} updated: {value}")
    else:
        body = urllib.parse.urlencode(
            {"link_url": link_url, "image_url": image_url, "name": NAME}
        ).encode()
        req(api, data=body, method="POST")
        print(f"Badge created: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
