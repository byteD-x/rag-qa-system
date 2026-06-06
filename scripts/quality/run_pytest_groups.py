from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = REPO_ROOT / "logs" / "quality"
DEFAULT_SUMMARY_OUTPUT = DEFAULT_LOG_DIR / "pytest-groups-summary.json"
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_HEARTBEAT_SECONDS = 30
DEFAULT_PYTEST_ARGS = ["-q", "-p", "pytest_asyncio.plugin"]


@dataclass(frozen=True)
class TestGroup:
    name: str
    args: list[str]


@dataclass(frozen=True)
class GroupResult:
    group: TestGroup
    exit_code: int
    elapsed_seconds: float
    timed_out: bool
    stdout_path: Path
    stderr_path: Path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run pytest in small groups with heartbeat output and hard timeouts.",
    )
    parser.add_argument("paths", nargs="*", default=["tests"], help="Test paths or node ids to run.")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--heartbeat-seconds", type=int, default=DEFAULT_HEARTBEAT_SECONDS)
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,
        help="Maximum pytest groups to run concurrently. Defaults to 1 for stable fail-fast behavior.",
    )
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--pytest-arg", action="append", default=[], help="Extra argument passed to pytest.")
    parser.add_argument("--python", default=sys.executable, help="Python executable used to run pytest.")
    parser.add_argument(
        "--enable-plugin-autoload",
        action="store_true",
        help="Allow pytest to auto-load all installed third-party plugins.",
    )
    return parser.parse_args(argv)


def build_groups(paths: list[str]) -> list[TestGroup]:
    if not paths:
        paths = ["tests"]

    groups: list[TestGroup] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            test_files = sorted(path.rglob("test_*.py"))
            groups.extend(TestGroup(_group_name(file), [str(file)]) for file in test_files)
        else:
            groups.append(TestGroup(_group_name(path), [raw_path]))
    return groups


def run_group(
    group: TestGroup,
    *,
    python: str,
    pytest_args: list[str],
    timeout_seconds: int,
    heartbeat_seconds: int,
    log_dir: Path,
    disable_plugin_autoload: bool = True,
) -> GroupResult:
    log_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{int(time.time() * 1000)}-{_safe_name(group.name)}"
    stdout_path = log_dir / f"pytest-{suffix}.out.log"
    stderr_path = log_dir / f"pytest-{suffix}.err.log"
    command = [python, "-m", "pytest", *pytest_args, *group.args]

    print(
        f"[pytest-group] start {group.name}: {_format_command(command)} "
        f"(timeout={timeout_seconds}s, logs={stdout_path} {stderr_path})",
        flush=True,
    )
    started = time.monotonic()
    process, stdout_handle, stderr_handle = _start_process(
        command,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        disable_plugin_autoload=disable_plugin_autoload,
    )
    timed_out = False
    next_heartbeat_at = started + max(1, heartbeat_seconds)

    try:
        while True:
            exit_code = process.poll()
            now = time.monotonic()
            elapsed = now - started
            if exit_code is not None:
                break
            if elapsed >= timeout_seconds:
                timed_out = True
                terminate_process_tree(process)
                exit_code = 124
                break
            if now >= next_heartbeat_at:
                print(
                    f"[pytest-group] still running {group.name}: elapsed={elapsed:.1f}s "
                    f"pid={process.pid}",
                    flush=True,
                )
                next_heartbeat_at = now + max(1, heartbeat_seconds)
            time.sleep(min(0.5, max(0.05, heartbeat_seconds / 10)))
    finally:
        stdout_handle.close()
        stderr_handle.close()

    elapsed = time.monotonic() - started
    if timed_out:
        print(
            f"[pytest-group] timeout {group.name}: elapsed={elapsed:.1f}s "
            f"logs={stdout_path} {stderr_path}",
            flush=True,
        )
    elif exit_code == 0:
        print(f"[pytest-group] passed {group.name}: elapsed={elapsed:.1f}s", flush=True)
    else:
        print(
            f"[pytest-group] failed {group.name}: exit_code={exit_code} "
            f"elapsed={elapsed:.1f}s logs={stdout_path} {stderr_path}",
            flush=True,
        )

    return GroupResult(
        group=group,
        exit_code=int(exit_code or 0),
        elapsed_seconds=elapsed,
        timed_out=timed_out,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def run_groups(
    groups: list[TestGroup],
    *,
    python: str,
    pytest_args: list[str],
    timeout_seconds: int,
    heartbeat_seconds: int,
    log_dir: Path,
    disable_plugin_autoload: bool = True,
    max_workers: int = 1,
) -> list[GroupResult]:
    workers = max(1, int(max_workers))
    if workers == 1:
        results: list[GroupResult] = []
        for group in groups:
            result = run_group(
                group,
                python=python,
                pytest_args=pytest_args,
                timeout_seconds=timeout_seconds,
                heartbeat_seconds=heartbeat_seconds,
                log_dir=log_dir,
                disable_plugin_autoload=disable_plugin_autoload,
            )
            results.append(result)
            if result.exit_code != 0:
                break
        return results

    results = []
    for batch_start in range(0, len(groups), workers):
        batch = groups[batch_start : batch_start + workers]
        batch_results: dict[int, GroupResult] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(batch)) as executor:
            future_to_index = {
                executor.submit(
                    run_group,
                    group,
                    python=python,
                    pytest_args=pytest_args,
                    timeout_seconds=timeout_seconds,
                    heartbeat_seconds=heartbeat_seconds,
                    log_dir=log_dir,
                    disable_plugin_autoload=disable_plugin_autoload,
                ): batch_start + offset
                for offset, group in enumerate(batch)
            }
            for future in concurrent.futures.as_completed(future_to_index):
                batch_results[future_to_index[future]] = future.result()

        results.extend(batch_results[index] for index in sorted(batch_results))
        if any(item.exit_code != 0 for item in batch_results.values()):
            break
    return results


def terminate_process_tree(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=3)
    except Exception:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception:
            process.kill()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    max_workers = max(1, int(args.max_workers))
    groups = build_groups(list(args.paths))
    if not groups:
        print("[pytest-group] no tests discovered", flush=True)
        write_summary(
            [],
            scheduled_groups=0,
            output_path=args.summary_output,
            max_workers=max_workers,
            elapsed_seconds=0.0,
        )
        return 0

    pytest_args = [*DEFAULT_PYTEST_ARGS, *args.pytest_arg]
    started = time.monotonic()
    results = run_groups(
        groups,
        python=args.python,
        pytest_args=pytest_args,
        timeout_seconds=max(1, int(args.timeout_seconds)),
        heartbeat_seconds=max(1, int(args.heartbeat_seconds)),
        log_dir=args.log_dir,
        disable_plugin_autoload=not args.enable_plugin_autoload,
        max_workers=max_workers,
    )
    elapsed = time.monotonic() - started
    _print_summary(results, elapsed_seconds=elapsed)
    write_summary(
        results,
        scheduled_groups=len(groups),
        output_path=args.summary_output,
        max_workers=max_workers,
        elapsed_seconds=elapsed,
    )
    failed = [item for item in results if item.exit_code != 0]
    return int(failed[0].exit_code) if failed else 0


def _start_process(
    command: list[str],
    *,
    stdout_path: Path,
    stderr_path: Path,
    disable_plugin_autoload: bool = True,
) -> tuple[subprocess.Popen[object], object, object]:
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    kwargs: dict[str, object] = {
        "cwd": str(REPO_ROOT),
        "stdout": stdout_handle,
        "stderr": stderr_handle,
        "text": True,
        "env": _subprocess_env(disable_plugin_autoload=disable_plugin_autoload),
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        process = subprocess.Popen(command, **kwargs)
        return process, stdout_handle, stderr_handle
    except Exception:
        stdout_handle.close()
        stderr_handle.close()
        raise


def _print_summary(results: list[GroupResult], *, elapsed_seconds: float | None = None) -> None:
    total = sum(item.elapsed_seconds for item in results) if elapsed_seconds is None else elapsed_seconds
    failed = [item for item in results if item.exit_code != 0]
    print(
        f"[pytest-group] summary groups={len(results)} failed={len(failed)} "
        f"elapsed={total:.1f}s",
        flush=True,
    )
    for item in failed:
        status = "timeout" if item.timed_out else f"exit_code={item.exit_code}"
        print(
            f"[pytest-group] failure {item.group.name}: {status} "
            f"logs={item.stdout_path} {item.stderr_path}",
            flush=True,
        )


def build_summary(
    results: list[GroupResult],
    *,
    scheduled_groups: int,
    max_workers: int = 1,
    elapsed_seconds: float | None = None,
) -> dict[str, object]:
    failed = [item for item in results if item.exit_code != 0]
    timed_out = [item for item in results if item.timed_out]
    total_elapsed = sum(item.elapsed_seconds for item in results) if elapsed_seconds is None else elapsed_seconds
    result_items = [_result_to_dict(item) for item in results]
    slowest = sorted(result_items, key=lambda item: float(item["elapsed_seconds"]), reverse=True)[:5]
    status = "passed"
    if failed:
        status = "failed"
    elif scheduled_groups > len(results):
        status = "incomplete"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "scheduled_groups": scheduled_groups,
        "completed_groups": len(results),
        "max_workers": max(1, int(max_workers)),
        "failed_groups": len(failed),
        "timed_out_groups": len(timed_out),
        "elapsed_seconds": round(total_elapsed, 4),
        "slowest_groups": slowest,
        "results": result_items,
    }


def write_summary(
    results: list[GroupResult],
    *,
    scheduled_groups: int,
    output_path: Path,
    max_workers: int = 1,
    elapsed_seconds: float | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = build_summary(
        results,
        scheduled_groups=scheduled_groups,
        max_workers=max_workers,
        elapsed_seconds=elapsed_seconds,
    )
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[pytest-group] summary_json={output_path}", flush=True)


def _result_to_dict(result: GroupResult) -> dict[str, object]:
    status = "timeout" if result.timed_out else ("passed" if result.exit_code == 0 else "failed")
    return {
        "group": result.group.name,
        "args": result.group.args,
        "status": status,
        "exit_code": result.exit_code,
        "elapsed_seconds": round(result.elapsed_seconds, 4),
        "timed_out": result.timed_out,
        "stdout_log": str(result.stdout_path),
        "stderr_log": str(result.stderr_path),
    }


def _subprocess_env(*, disable_plugin_autoload: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if disable_plugin_autoload:
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def _group_name(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)[:120]


def _format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


if __name__ == "__main__":
    raise SystemExit(main())
