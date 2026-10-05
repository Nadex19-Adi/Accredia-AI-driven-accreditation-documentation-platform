"""
Optional RQ worker.

The API is fully functional without Redis — long-running work falls back to
FastAPI BackgroundTasks, which is fine for a single-node deployment. Run this
worker (and point the API at Redis) when you want durable, retryable jobs.

Start:
    .venv\\Scripts\\python.exe -m app.workers.rq_worker

Enqueue from application code:
    from app.workers.rq_worker import enqueue
    enqueue("extract", project_id)
"""
import sys

from app.core.config import settings
from app.services import pipeline

QUEUE_NAME = "accredraft"

TASKS = {
    "process": pipeline.process_files,
    "extract": pipeline.run_extraction,
    "validate": pipeline.run_validation,
    "generate": pipeline.generate_document,
}


def get_queue():
    from redis import Redis
    from rq import Queue

    return Queue(QUEUE_NAME, connection=Redis.from_url(settings.REDIS_URL))


def enqueue(task: str, *args, **kwargs):
    """Enqueue a pipeline task. Raises KeyError for an unknown task name."""
    fn = TASKS[task]
    return get_queue().enqueue(fn, *args, **kwargs)


def main() -> int:
    try:
        from redis import Redis
        from rq import Queue, Worker
    except ImportError:
        print("rq/redis not installed. pip install -r requirements.txt", file=sys.stderr)
        return 1

    connection = Redis.from_url(settings.REDIS_URL)
    try:
        connection.ping()
    except Exception as exc:
        print(f"Cannot reach Redis at {settings.REDIS_URL}: {exc}", file=sys.stderr)
        return 1

    queue = Queue(QUEUE_NAME, connection=connection)
    print(f"RQ worker listening on '{QUEUE_NAME}' ({settings.REDIS_URL})")
    Worker([queue], connection=connection).work()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
