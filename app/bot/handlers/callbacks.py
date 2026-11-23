import logging
from telegram import Update
from telegram.ext import ContextTypes
from app.db.repository import get_credentials
from app.odoo.task_client import TaskOdooClient

logger = logging.getLogger(__name__)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data

    # Ignore setup_mode_ and skip_ callbacks as they are handled by setup ConversationHandler
    if data.startswith("setup_mode_") or data in ("skip_att_step", "skip_task_step"):
        return

    await query.answer()
    user_id = update.effective_user.id
    creds = get_credentials(user_id)

    if not creds or not creds.get("task_odoo_url"):
        await query.message.reply_text("⚠️ Tasks & Timesheets instance is not configured. Please run /setup.")
        return

    try:
        task_client = TaskOdooClient(
            url=creds["task_odoo_url"],
            db=creds["task_odoo_db"],
            user=creds["task_odoo_user"],
            key=creds["task_odoo_key"]
        )
    except Exception as e:
        await query.message.reply_text(f"❌ Could not connect to Tasks instance: {str(e)}")
        return

    if data.startswith("quicklog_"):
        parts = data.split("_")
        task_id = int(parts[1])
        hours = float(parts[2])

        res = task_client.log_timesheet(task_id=task_id, hours=hours, description="Logged via Telegram Agent")
        if res.get("success"):
            await query.message.reply_text(f"✅ Logged {hours}h on task #{task_id} successfully!")
        else:
            await query.message.reply_text(f"❌ Failed to log timesheet: {res.get('error')}")

    elif data.startswith("complete_"):
        task_id = int(data.split("_")[1])
        res = task_client.complete_task(task_id=task_id)
        if res.get("success"):
            await query.message.reply_text(f"🎉 Task #{task_id} marked as Completed!")
        else:
            await query.message.reply_text(f"❌ Failed to complete task: {res.get('error')}")
