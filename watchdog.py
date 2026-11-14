#!/usr/bin/env python3
"""Watchdog for sentry-cycle: does the journal still smell alive?

Sentry's own cron is best-effort on GitHub Actions — runs can be delayed or dropped with no
notification, and if the scheduler forgets the workflow entirely there is no red X anywhere.
This runs hourly on its own schedule: it reads the last journal entry in the repo and exits
NON-ZERO (red run -> GitHub emails you) when the brain has been silent too long.

Stdlib only. No secrets needed (uses the run's own GITHUB_TOKEN, injected by the workflow).
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("GITHUB_REPOSITORY") or "akramsakib/sentry"
PATH = "journal.md"
STALE_HOURS = float(os.environ.get("SENTRY_STALE_HOURS") or "3")
LAST_RE = re.compile(r"\*\*(\d{2})-(\d{2}) (\d{2}):(\d{2}) UTC\*\*")


def fetch_journal():
    url = f"https://api.github.com/repos/{REPO}/contents/{PATH}"
    tok = os.environ.get("GITHUB_TOKEN")
    hdr = {"Accept": "application/vnd.github+json", "User-Agent": "sentry-watchdog/1.0"}
    if tok:
        hdr["Authorization"] = "Bearer " + tok
    with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=20) as r:
        return json.loads(r.read())


def dispatch(which, msg):
    """Fire workflow_dispatch for this repo's own workflow. No-op without a token."""
    tok = os.environ.get("GITHUB_TOKEN")
    if not tok:
        return False
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{which}/dispatches"
    body = json.dumps({"ref": "main", "reason": msg}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json",
        "Content-Type": "application/json", "User-Agent": "sentry-watchdog/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 204)
    except Exception:                                           # noqa: BLE001
        return False


def main():
    try:
        meta = fetch_journal()
        body = base64_text(meta)                    # journal.md is prose, not JSON
    except Exception as exc:                                    # noqa: BLE001
        print(f"WATCHDOG ALERT: cannot read {PATH} from {REPO}: {exc}")
        return 1
    stamps = LAST_RE.findall(body)
    if not stamps:
        print(f"WATCHDOG ALERT: {PATH} has no cycle timestamps — the brain never wrote a cycle")
        return 1
    mm, dd, hh, mi = (int(x) for x in stamps[-1])
    year = datetime.now(timezone.utc).year                      # journal rolls at year boundary
    try:
        last = datetime(year, mm, dd, hh, mi, tzinfo=timezone.utc)
    except ValueError:
        print(f"WATCHDOG ALERT: unparseable journal timestamp {mm}-{dd} {hh}:{mi}")
        return 1
    if last > datetime.now(timezone.utc):                        # December entry seen in January
        last = last.replace(year=year - 1)

    age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600.0
    tail = [l for l in body.splitlines() if l.strip()][-1][:110]
    if age_h > STALE_HOURS:
        print(f"WATCHDOG ALERT: sentry-cycle silent for {age_h:.1f} h "
              f"(threshold {STALE_HOURS:g} h). Last entry: {tail}")
        print("Check: Actions tab (disabled workflow? queued runs?), then run it manually.")
        # self-heal: a tick needs no secrets (workflow_dispatch is one of the two events a
        # GITHUB_TOKEN may legitimately fire), so a red run also restarts the brain.
        if dispatch("scan.yml", "self-heal after stale journal"):
            print("  -> dispatched a fresh sentry-cycle run")
        return 1
    print(f"watchdog ok · last cycle {age_h:.1f} h ago · {tail}")
    return 0


def base64_text(meta):
    import base64
    raw = base64.b64decode(meta.get("content") or "")
    # trades/journal are utf-8 text; decode tolerates the odd broken byte
    return raw.decode("utf-8", "replace")


if __name__ == "__main__":
    sys.exit(main())
