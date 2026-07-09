FROM welyne-hr-api:latest

WORKDIR /app

CMD ["celery", "-A", "orchestrator.celery_app", "worker", "--loglevel=info", "--concurrency=2"]
