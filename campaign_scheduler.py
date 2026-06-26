import logging
import os
import threading
import time
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

LOG_FILE = os.getenv('CAMPAIGN_SCHEDULER_LOG', 'campaign_scheduler.log')
INTERVAL_SECONDS = 60 * 60  # 1 hour

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)


def run_scheduler_task():
    from app import run_daily_campaign

    logging.info('Scheduler started. Checking campaign status...')
    try:
        result = run_daily_campaign()
        logging.info(
            'Campaign run result: sent=%s attempted=%s message=%s',
            result.get('sent'),
            result.get('attempted'),
            result.get('message'),
        )
    except Exception as exc:
        logging.exception('Campaign scheduler encountered an error: %s', exc)


def scheduler_loop():
    while True:
        now = datetime.now()
        logging.info('Hourly scheduler tick at %s', now.strftime('%Y-%m-%d %H:%M:%S'))
        run_scheduler_task()
        time.sleep(INTERVAL_SECONDS)


def start_campaign_scheduler():
    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()
    logging.info('Campaign scheduler thread started, running every %s seconds.', INTERVAL_SECONDS)
