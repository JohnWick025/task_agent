"""
run_polling.py - Local development runner using Telegram Long Polling.
Use this for instant local testing without setting up Webhooks or public URLs!
"""

import logging
from app.db.session import init_db
from app.bot.telegram_app import get_telegram_app

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Initializing database...")
    init_db()

    logger.info("Starting Telegram Bot in Long Polling mode...")
    app = get_telegram_app()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
