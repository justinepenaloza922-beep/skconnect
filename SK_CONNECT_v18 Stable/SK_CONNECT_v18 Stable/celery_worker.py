import os
from celery import Celery

BROKER = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
BACKEND = os.environ.get('CELERY_RESULT_BACKEND', BROKER)

celery_app = Celery('skconnect', broker=BROKER, backend=BACKEND)

# beat schedule: run every 10 seconds for responsive scheduled announcements
celery_app.conf.beat_schedule = {
    'process-scheduled-announcements-every-10-seconds': {
        'task': 'tasks.announcement_tasks.process_scheduled_announcements',
        'schedule': 10.0,
    }
}
celery_app.conf.timezone = 'UTC'

# Ensure the scheduled announcement task module is imported so the task is registered
import tasks.announcement_tasks  # noqa: F401

if __name__ == '__main__':
    celery_app.start()
