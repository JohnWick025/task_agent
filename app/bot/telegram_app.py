import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from app.config import settings
from app.bot.handlers.setup_wizard import get_setup_handler
from app.bot.handlers.commands import (
    start_cmd,
    help_cmd,
    clock_in_cmd,
    clock_out_cmd,
    status_cmd,
    tasks_cmd,
    timesheet_cmd,
    handle_message,
)
from app.bot.handlers.callbacks import handle_callback_query

logger = logging.getLogger(__name__)

_bot_app: Application = None


def get_telegram_app() -> Application:
    global _bot_app
    if _bot_app is None:
        token = settings.TELEGRAM_BOT_TOKEN or "dummy-token-for-dev"
        _bot_app = Application.builder().token(token).build()

        # Register Setup Wizard first so it intercepts setup steps
        _bot_app.add_handler(get_setup_handler())

        # Register Commands
        _bot_app.add_handler(CommandHandler("start", start_cmd))
        _bot_app.add_handler(CommandHandler("help", help_cmd))
        _bot_app.add_handler(CommandHandler("clockin", clock_in_cmd))
        _bot_app.add_handler(CommandHandler("clockout", clock_out_cmd))
        _bot_app.add_handler(CommandHandler("status", status_cmd))
        _bot_app.add_handler(CommandHandler("tasks", tasks_cmd))
        _bot_app.add_handler(CommandHandler("timesheets", timesheet_cmd))

        # Register Callback Query handler (inline buttons)
        _bot_app.add_handler(CallbackQueryHandler(handle_callback_query))

        # Register generic text message handler for buttons & NLP agent
        _bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return _bot_app


async def process_telegram_update(update_json: dict) -> None:
    """Processes an incoming webhook update dict from Telegram."""
    app = get_telegram_app()
    update = Update.de_json(data=update_json, bot=app.bot)
    await app.process_update(update)
