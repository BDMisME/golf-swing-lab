from redis import Redis
from rq import Queue, SimpleWorker

from apps.api.config import get_settings


def main() -> None:
    """啟動 RQ Worker 監聽 gsl-analysis 與 gsl-exports 佇列。"""
    settings = get_settings()
    redis_conn = Redis.from_url(settings.redis_url)
    queues = [
        Queue("gsl-analysis", connection=redis_conn),
        Queue("gsl-exports", connection=redis_conn),
        Queue("gsl-tracer", connection=redis_conn),
    ]
    worker = SimpleWorker(queues, connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
