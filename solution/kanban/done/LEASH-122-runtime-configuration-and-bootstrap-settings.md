# LEASH-122: Runtime configuration and bootstrap settings

**Status**: DONE
**Priority**: P0
**Type**: feature
**Estimated Effort**: M
**Milestone**: M3 — Durable fake-API integration
**Rule source**: Viseca contract
**Decisions**: DEC-008
**Parent**: LEASH-004
**Task ID**: 004-T9
**Blocked by**: LEASH-050
**Blocks**: LEASH-045, LEASH-052, LEASH-126, LEASH-127, LEASH-128
**Updated**: 2026-09-23

## Description
Typed configuration: environment settings validated at startup, and settings read from /v1/bootstrap (timeouts, human window, limits, features, versions) distributed to the worker, deadline budget, sweeper and app.

## Business Value
Timeouts must follow the platform, not our constants.

## Acceptance Criteria
- [x] Missing or invalid configuration fails at startup with a clear message.
- [x] Bootstrap values reach the watchdog margin, the ask expiry and the app.
- [x] API and data versions are checked for compatibility.
- [x] Secrets are redacted from logs.

## Technical Approach
`config.py` (Pydantic settings) + bootstrap loader.

### Dependencies
- Needs LEASH-050.
- Blocks LEASH-045.
- Blocks LEASH-052.
- Blocks LEASH-126.
- Blocks LEASH-127.
- Blocks LEASH-128.

## Testing Requirements
Write first: `test_human_window_comes_from_bootstrap`, `test_api_key_never_logged`.

## Related Files
- `solution/engine/src/leash/config.py`
- `solution/engine/tests/test_config.py`

## Out of scope
- Hot-reloading configuration.

## Review log

### 2026-09-23 — independent agent review (round 1)
- [x] met — criteria 1–3 (clear startup errors naming each variable; bootstrap values exposed for watchdog, ask expiry and app with visible defaults; api 0.x / data saw26 check with healthz fallback).
- [ ] not met — criterion 4: redaction installed before handlers missed child-logger records, and tracebacks were never redacted.
Verdict: returned to in-progress. Fix: redaction moved to the log-record factory (covers every logger and later handlers; pre-formats and redacts tracebacks and stack info); `install_redaction` returns an uninstaller. Tests added for child logger installed-before-handlers, tracebacks, and uninstall.

### 2026-09-23 — independent agent review (round 2)
- [x] met — criteria 1–3; round-1 redaction gaps fixed (child loggers, tracebacks, stack info, later handlers).
- [ ] not met — criterion 4: database passwords in valid URL forms not redacted (percent-encoded, in the query string, containing '@'); `extra=` fields bypass redaction; records rebuilt with `logging.makeLogRecord` bypass it. Side effect: a malformed log call now raised in the caller.
Verdict: returned to in-progress.

### 2026-09-23 — independent agent review (round 3)
- [x] met — criteria 1–3; round-2 leaks fixed (URL forms, string extras, makeLogRecord, malformed calls); many further paths clean.
- [ ] not met — criterion 4: non-string extras (dict/list/object) leak; '+' in a query-string password; other encodings (hex case, URL-encoded API key, repr-escaped); Logger subclasses overriding makeRecord without super; hand-built LogRecords; uninstall only correct in reverse order.
Verdict: returned to in-progress.

### 2026-09-23 — independent agent review (round 4)
- [x] met — criteria 1–3 (re-verified).
- [x] met — criterion 4: all round 1–3 leak paths clean; standard usage probed (handlers with/without formatters, Formatter subclasses calling super, LoggerAdapter, Queue handler/listener, 20 threads, warnings, chained exceptions, stack info, makeLogRecord, malformed calls, uninstall in any order).
- Residual risk (outside what a redaction layer can guarantee): formatter-less transport handlers (HTTPHandler, SocketHandler pickles) with non-string extras or raw exc_info; hand-written formatters that skip super().format; JSON/ascii-escaped secrets; passwords of 1–2 characters. Also: redaction is not yet installed at startup — LEASH-127 (deployment) must call it.
Verdict: moved to review; moved to done on the product owner's standing instruction for this run.
