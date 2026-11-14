# The Mac crypto book (v4.7.2)

`~/hermes_sentry/crypto/` on the user's Mac runs `crypto_loop.py` under launchd
(`com.hermes.sentry.crypto`, RunAtLoad + KeepAlive, cycle 300 s) — the same engine as this repo
and the MT5 forex build, executing straight against OKX REST. Files to deploy into that folder:
`sentry_core.py run_cycle.py broker_okx.py broker_ledger.py config.json crypto_loop.py okx.env`.
The folder's config differs from the repo's in exactly one line: `auto_ack_on_key: true` (this
is the armed book; the repo mirror is not). Keys: `okx.env` only, chmod 600, never committed.
Desk alerts reuse the forex build's wiring: `alerts.outbox` + `[DESK-WAKE]` POST to the jarvis
bridge on 127.0.0.1:8768. Kill switch: `launchctl bootout gui/$(id -u)/com.hermes.sentry.crypto`
— open positions keep their venue-side TP/SL.
