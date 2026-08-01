#!/usr/bin/env python3
"""Parent watchdog and interrupted-run recovery for SignalCloud native stress.

The watchdog intentionally owns only process safety and report preservation. The native
benchmark remains the source of renderer/game telemetry and machine-profile decisions.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

STATE_NAME = "RUN_STATE.json"
HEARTBEAT_NAME = "WATCHDOG_HEARTBEAT.json"
JOURNAL_NAME = "STAGE_JOURNAL.csv"
RECOVERY_NAME = "INTERRUPTED_RUN_RECOVERY.json"
FINAL_REPORT_NAME = "NATIVE_STRESS_REPORT.md"
FINAL_RESULTS_NAME = "NATIVE_STRESS_RESULTS.csv"
GLOBAL_STATE = "native_stress_watchdog.json"
CLEAN_REQUEST = "native_stress_watchdog_stop.request"
HARD_REQUEST = "native_stress_watchdog_abort.request"


@dataclass(frozen=True)
class WatchdogPolicy:
    heartbeat_timeout: float = 8.0
    generation_timeout: float = 90.0
    startup_timeout: float = 45.0
    clean_stop_grace: float = 8.0
    poll_seconds: float = 0.25




def heartbeat_timeout_for_phase(phase: str, policy: WatchdogPolicy) -> float:
    """Return the phase-aware timeout without weakening normal heartbeat checks.

    Point-cloud generation and GPU upload are intentionally synchronous in the native
    benchmark. Large 16M/20M stages can legitimately spend more than the ordinary
    rendering heartbeat timeout inside that bounded operation. Only the explicit
    ``generating`` phase receives the longer user-configurable allowance.
    """
    return policy.generation_timeout if phase.strip().lower() == "generating" else policy.heartbeat_timeout

def _atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _safe_session(root: Path, session: Path) -> Path:
    report_root = (root / "reports" / "native_stress_runs").resolve(strict=False)
    resolved = session.resolve(strict=False)
    try:
        resolved.relative_to(report_root)
    except ValueError as exc:
        raise ValueError("watchdog session escapes reports/native_stress_runs") from exc
    return resolved


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_journal(session: Path) -> list[dict[str, str]]:
    path = session / JOURNAL_NAME
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            return [dict(row) for row in csv.DictReader(stream)]
    except (OSError, csv.Error):
        return []


def _plain_pointer(root: Path, session: Path) -> None:
    _atomic_text(root / "reports" / "native_stress_latest_path.txt", str(session) + "\n")


def _journal_table(rows: Iterable[dict[str, str]]) -> str:
    lines = [
        "| Mode | Stage | Points | Entities | Avg FPS | Route m | Result | Failure |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        passed = row.get("passed", "0") in {"1", "true", "TRUE", "PASS"}
        failure = row.get("failure", "").replace("|", "/")
        lines.append(
            f"|{row.get('mode', '?')}|{row.get('stage', '?')}|{row.get('points', '0')}|"
            f"{row.get('entities', '0')}|{row.get('avg_fps', '0')}|"
            f"{row.get('route_distance_delta', '0')}|{'PASS' if passed else 'LIMIT/FAIL'}|{failure}|"
        )
    return "\n".join(lines)




def _reconcile_report_reason(report: Path, reason: str) -> None:
    """Make parent watchdog provenance authoritative in an existing child report."""
    try:
        lines = report.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    status_line = "- Run status: **INTERRUPTED — NOT ELIGIBLE FOR PROFILE PROMOTION**"
    reason_line = f"- Completion reason: `{reason}`"
    watchdog_line = f"- Watchdog recovery reason: `{reason}`"
    saw_status = False
    saw_reason = False
    saw_watchdog = False
    for index, line in enumerate(lines):
        if line.startswith("- Run status:"):
            lines[index] = status_line
            saw_status = True
        elif line.startswith("- Completion reason:"):
            lines[index] = reason_line
            saw_reason = True
        elif line.startswith("- Watchdog recovery reason:"):
            lines[index] = watchdog_line
            saw_watchdog = True
    insertion = 2 if len(lines) >= 2 else len(lines)
    if not saw_status:
        lines.insert(insertion, status_line)
        insertion += 1
    if not saw_reason:
        lines.insert(insertion, reason_line)
        insertion += 1
    if not saw_watchdog:
        lines.insert(insertion, watchdog_line)
    _atomic_text(report, "\n".join(lines).rstrip() + "\n")

def recover_partial_report(root: Path, session: Path, reason: str, *, child_exit_code: int | None = None) -> Path:
    """Preserve a readable report from an interrupted session without touching profiles."""
    root = root.resolve()
    session = _safe_session(root, session)
    session.mkdir(parents=True, exist_ok=True)
    report = session / FINAL_REPORT_NAME
    rows = _read_journal(session)
    live = _read_json(session / "LIVE_SNAPSHOT.json")
    if not live:
        live = _read_json(root / "reports" / "native_stress_live.json")
    state = _read_json(session / STATE_NAME)
    started = state.get("started_utc", "unknown")
    stage = live.get("stage", state.get("current_stage", "unknown"))
    location = live.get("location", "unknown")
    heartbeat_age = None
    heartbeat = session / HEARTBEAT_NAME
    if heartbeat.exists():
        heartbeat_age = max(0.0, time.time() - heartbeat.stat().st_mtime)

    if not report.is_file():
        text = [
            "# SignalCloud Engine-Native Stress Report — Recovered Partial Run",
            "",
            "- Run status: **INTERRUPTED — NOT ELIGIBLE FOR PROFILE PROMOTION**",
            f"- Recovery reason: `{reason}`",
            f"- Started: `{started}`",
            f"- Last stage: `{stage}`",
            f"- Last location: `{location}`",
            f"- Completed journal stages: {len(rows)}",
        ]
        if child_exit_code is not None:
            text.append(f"- Child exit code: `{child_exit_code}`")
        if heartbeat_age is not None:
            text.append(f"- Last heartbeat age at recovery: {heartbeat_age:.2f} seconds")
        text.extend([
            "- Active and previous-known-good machine profiles were left unchanged.",
            "",
            "## Preserved stage evidence",
            "",
            _journal_table(rows) if rows else "No stage had completed before interruption.",
            "",
            "## Last telemetry snapshot",
            "",
            "```json",
            json.dumps(live, indent=2, sort_keys=True) if live else "{}",
            "```",
            "",
        ])
        _atomic_text(report, "\n".join(text))

    _reconcile_report_reason(report, reason)

    journal = session / JOURNAL_NAME
    results = session / FINAL_RESULTS_NAME
    if journal.is_file() and not results.is_file():
        _atomic_text(results, journal.read_text(encoding="utf-8", errors="replace"))

    receipt = {
        "schema": "signalcloud_native_stress_recovery",
        "schema_version": 1,
        "status": "interrupted",
        "reason": reason,
        "child_exit_code": child_exit_code,
        "completed_stage_rows": len(rows),
        "profile_promotion_allowed": False,
        "profiles_modified": False,
        "report": str(report),
        "recovered_unix": int(time.time()),
    }
    _atomic_json(session / RECOVERY_NAME, receipt)
    state.update({
        "state": "interrupted",
        "reason": reason,
        "child_exit_code": child_exit_code,
        "profile_promotion_allowed": False,
        "completed_stage_rows": len(rows),
        "finished_unix": int(time.time()),
    })
    _atomic_json(session / STATE_NAME, state)
    _plain_pointer(root, session)
    return report


def recover_orphaned_sessions(root: Path, *, stale_after: float = 30.0) -> list[Path]:
    """Recover sessions left in RUNNING state after a launcher/system interruption."""
    root = root.resolve()
    report_root = root / "reports" / "native_stress_runs"
    recovered: list[Path] = []
    if not report_root.is_dir():
        return recovered
    now = time.time()
    for session in sorted(report_root.iterdir()):
        if not session.is_dir() or (session / FINAL_REPORT_NAME).is_file():
            continue
        state = _read_json(session / STATE_NAME)
        if state.get("state") not in {"starting", "running", "stopping"}:
            continue
        heartbeat = session / HEARTBEAT_NAME
        reference = heartbeat if heartbeat.exists() else session / STATE_NAME
        try:
            age = max(0.0, now - reference.stat().st_mtime)
        except OSError:
            age = stale_after + 1.0
        if age < stale_after:
            continue
        recover_partial_report(root, session, "ORPHANED_PARENT_OR_SYSTEM_INTERRUPTION")
        recovered.append(session)
    return recovered


def heartbeat_is_stale(path: Path, *, now: float | None = None, timeout: float = 8.0) -> bool:
    if not path.is_file():
        return True
    current = time.time() if now is None else now
    return current - path.stat().st_mtime > timeout


def _make_session(root: Path) -> Path:
    report_root = root / "reports" / "native_stress_runs"
    report_root.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time())
    session = report_root / f"native_{stamp}_{os.getpid()}"
    counter = 1
    while session.exists():
        session = report_root / f"native_{stamp}_{os.getpid()}_{counter}"
        counter += 1
    session.mkdir(parents=True)
    return session.resolve()


def _request_present(root: Path, name: str) -> bool:
    return (root / "reports" / name).is_file()


def _remove_requests(root: Path) -> None:
    for name in (CLEAN_REQUEST, HARD_REQUEST):
        (root / "reports" / name).unlink(missing_ok=True)


def _terminate(process: subprocess.Popen[Any], *, hard: bool, grace: float) -> None:
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGTERM)
    except ProcessLookupError:
        return
    if hard:
        grace = min(grace, 1.0)
    try:
        process.wait(timeout=max(0.1, grace))
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            pass


def run_watchdog(root: Path, child_command: list[str], policy: WatchdogPolicy) -> int:
    root = root.resolve()
    if not child_command:
        raise ValueError("watchdog requires a benchmark child command")
    recovered = recover_orphaned_sessions(root)
    session = _make_session(root)
    heartbeat = session / HEARTBEAT_NAME
    child_stop = session / "STOP.request"
    global_state = root / "reports" / GLOBAL_STATE
    _remove_requests(root)

    command = list(child_command)
    command.extend([
        f"--session-dir={session}",
        f"--stop-file={child_stop}",
        f"--heartbeat-file={heartbeat}",
    ])
    started = time.time()
    state = {
        "schema": "signalcloud_native_stress_watchdog",
        "schema_version": 1,
        "state": "starting",
        "session_dir": str(session),
        "started_unix": int(started),
        "heartbeat_timeout_seconds": policy.heartbeat_timeout,
        "generation_timeout_seconds": policy.generation_timeout,
        "orphaned_sessions_recovered": [str(item) for item in recovered],
    }
    _atomic_json(session / STATE_NAME, state)
    _atomic_json(global_state, state)

    try:
        process = subprocess.Popen(command, cwd=root)
    except OSError as exc:
        recover_partial_report(root, session, f"CHILD_LAUNCH_FAILED: {exc}")
        state.update({"state": "launch_failed", "reason": str(exc)})
        _atomic_json(global_state, state)
        return 71

    state.update({"state": "running", "child_pid": process.pid})
    _atomic_json(session / STATE_NAME, state)
    _atomic_json(global_state, state)
    stop_kind: str | None = None
    stale_since: float | None = None

    while process.poll() is None:
        now = time.time()
        if _request_present(root, HARD_REQUEST):
            stop_kind = "USER_HARD_ABORT"
            _terminate(process, hard=True, grace=policy.clean_stop_grace)
            break
        if _request_present(root, CLEAN_REQUEST):
            stop_kind = "USER_CLEAN_STOP"
            child_stop.touch()
            state.update({"state": "stopping", "reason": stop_kind})
            _atomic_json(global_state, state)
            try:
                process.wait(timeout=policy.clean_stop_grace)
            except subprocess.TimeoutExpired:
                stop_kind = "CLEAN_STOP_TIMEOUT"
                _terminate(process, hard=False, grace=2.0)
            break

        age = None
        heartbeat_phase = ""
        active_timeout = policy.heartbeat_timeout
        if heartbeat.exists():
            age = max(0.0, now - heartbeat.stat().st_mtime)
            heartbeat_phase = str(_read_json(heartbeat).get("phase", "") or "")
            active_timeout = heartbeat_timeout_for_phase(heartbeat_phase, policy)
            if age > active_timeout:
                stale_since = stale_since or now
                stop_kind = (
                    "WATCHDOG_GENERATION_TIMEOUT"
                    if heartbeat_phase.strip().lower() == "generating"
                    else "WATCHDOG_HEARTBEAT_TIMEOUT"
                )
                _terminate(process, hard=False, grace=2.0)
                break
        elif now - started > policy.startup_timeout:
            stop_kind = "WATCHDOG_STARTUP_TIMEOUT"
            _terminate(process, hard=False, grace=2.0)
            break

        state.update({
            "state": "running",
            "child_pid": process.pid,
            "heartbeat_age_seconds": age,
            "heartbeat_seen": heartbeat.exists(),
            "heartbeat_phase": heartbeat_phase,
            "active_timeout_seconds": active_timeout,
            "updated_unix": int(now),
        })
        _atomic_json(global_state, state)
        time.sleep(policy.poll_seconds)

    code = process.poll()
    if code is None:
        try:
            code = process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            _terminate(process, hard=True, grace=0.5)
            code = process.poll()
    code = int(code if code is not None else 72)

    report = session / FINAL_REPORT_NAME
    run_state = _read_json(session / STATE_NAME)
    native_reason = str(run_state.get("reason", ""))
    completed = report.is_file() and run_state.get("state") == "completed" and code == 0
    if completed:
        state.update({"state": "completed", "child_exit_code": code, "finished_unix": int(time.time())})
        _atomic_json(global_state, state)
        _plain_pointer(root, session)
        _remove_requests(root)
        return 0

    reason = stop_kind or native_reason or ("PROCESS_CRASH" if code != 0 else "INCOMPLETE_OUTPUT")
    recover_partial_report(root, session, reason, child_exit_code=code)
    state.update({
        "state": "interrupted",
        "reason": reason,
        "child_exit_code": code,
        "finished_unix": int(time.time()),
        "partial_report": str(session / FINAL_REPORT_NAME),
    })
    _atomic_json(global_state, state)
    _remove_requests(root)
    if reason == "USER_CLEAN_STOP":
        return 10
    if reason == "USER_HARD_ABORT":
        return 11
    if reason.startswith("WATCHDOG") or reason == "CLEAN_STOP_TIMEOUT":
        return 70
    return code if code != 0 else 72


def _parse_args(argv: list[str]) -> argparse.Namespace:
    # argparse REMAINDER consumes option-looking tokens after the first positional.
    # Split the parent watchdog options from the child command explicitly so paths
    # and policy flags remain unambiguous on every supported shell.
    child: list[str] = []
    parent_argv = list(argv)
    if "--" in parent_argv:
        split_at = parent_argv.index("--")
        child = parent_argv[split_at + 1 :]
        parent_argv = parent_argv[:split_at]

    parser = argparse.ArgumentParser(description="SignalCloud engine-native stress watchdog")
    parser.add_argument("root", type=Path)
    parser.add_argument("--heartbeat-timeout", type=float, default=8.0)
    parser.add_argument("--generation-timeout", type=float, default=90.0)
    parser.add_argument("--startup-timeout", type=float, default=45.0)
    parser.add_argument("--clean-stop-grace", type=float, default=8.0)
    parser.add_argument("--recover-orphans", action="store_true")
    args = parser.parse_args(parent_argv)
    args.child = child
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.recover_orphans and not args.child:
        recovered = recover_orphaned_sessions(args.root, stale_after=0.0)
        for session in recovered:
            print(f"Recovered interrupted stress session: {session}")
        return 0
    if not args.child:
        print("ERROR: child command is required after --", file=sys.stderr)
        return 2
    policy = WatchdogPolicy(
        heartbeat_timeout=max(2.0, args.heartbeat_timeout),
        generation_timeout=max(max(2.0, args.heartbeat_timeout), args.generation_timeout),
        startup_timeout=max(5.0, args.startup_timeout),
        clean_stop_grace=max(1.0, args.clean_stop_grace),
    )
    return run_watchdog(args.root, list(args.child), policy)


if __name__ == "__main__":
    raise SystemExit(main())
