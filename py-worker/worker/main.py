from __future__ import annotations

import time

from redis import Redis
from redis.exceptions import RedisError

from worker.config import build_worker_config
from worker.processor import IngestProcessor


def run() -> None:
    cfg = build_worker_config()
    redis_cli = Redis.from_url(cfg.redis_url, decode_responses=True)
    processor = IngestProcessor(cfg)

    print(
        "[py-worker] started "
        f"queue={cfg.ingest_queue_key} "
        f"poll_interval={cfg.poll_interval_seconds}s "
        f"max_retries={cfg.worker_max_retries}",
        flush=True,
    )

    while True:
        try:
            item = redis_cli.blpop(cfg.ingest_queue_key, timeout=cfg.poll_interval_seconds)
            if item is None:
                continue

            _, job_id = item
            ok, status = processor.process_job(job_id)
            print(f"[py-worker] job={job_id} processed ok={ok} status={status}", flush=True)
            if status == "retry":
                redis_cli.rpush(cfg.ingest_queue_key, job_id)

        except RedisError as exc:
            print(f"[py-worker] redis error: {exc}", flush=True)
            time.sleep(cfg.poll_interval_seconds)
        except Exception as exc:  # noqa: BLE001
            print(f"[py-worker] unexpected error: {exc}", flush=True)
            time.sleep(cfg.poll_interval_seconds)


if __name__ == "__main__":
    run()