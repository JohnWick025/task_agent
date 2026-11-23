import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.session import init_db
from app.bot.telegram_app import get_telegram_app, process_telegram_update

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Database...")
    init_db()

    bot_app = get_telegram_app()
    await bot_app.initialize()

    # If Webhook URL is configured, register with Telegram
    if settings.TELEGRAM_WEBHOOK_URL:
        logger.info(f"Setting Telegram Webhook to: {settings.TELEGRAM_WEBHOOK_URL}")
        try:
            await bot_app.bot.set_webhook(
                url=settings.TELEGRAM_WEBHOOK_URL,
                secret_token=settings.TELEGRAM_SECRET_TOKEN or None,
                drop_pending_updates=True
            )
            logger.info("Telegram Webhook registered successfully.")
        except Exception as e:
            logger.error(f"Failed to register webhook: {e}")
    else:
        logger.warning("TELEGRAM_WEBHOOK_URL is not set. Running without automatic webhook registration.")

    await bot_app.start()

    yield

    # Shutdown
    logger.info("Shutting down Telegram Bot...")
    await bot_app.stop()
    await bot_app.shutdown()


app = FastAPI(
    title="Multi-User Telegram Odoo Agent",
    description="CrewAI and NVIDIA NIM powered dual-Odoo Telegram assistant for Attendance and Tasks",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    from app.ai.llm_provider import llm_provider
    return {
        "service": "Telegram Odoo Agent",
        "status": "online",
        "providers_configured": [p.name for p in llm_provider.providers],
        "active_provider": llm_provider.active_provider.name,
        "webhook_enabled": bool(settings.TELEGRAM_WEBHOOK_URL),
    }


@app.get("/health")
async def health_check():
    """Endpoint for Render or Uptime pinging to prevent cold sleep."""
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str = Header(None)
):
    """
    Receives incoming updates from Telegram via Webhook.
    Returns 200 OK immediately and processes the message asynchronously
    to eliminate timeout drops during LLM execution.
    """
    # Verify secret token if configured
    if settings.TELEGRAM_SECRET_TOKEN and x_telegram_bot_api_secret_token != settings.TELEGRAM_SECRET_TOKEN:
        logger.warning("Rejected webhook update: Invalid secret token.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret token"
        )

    try:
        update_json = await request.json()
        # Dispatch processing to background task to respond to Telegram immediately
        background_tasks.add_task(process_telegram_update, update_json)
        return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "accepted"})
    except Exception as e:
        logger.exception("Error receiving telegram update")
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"error": str(e)})
