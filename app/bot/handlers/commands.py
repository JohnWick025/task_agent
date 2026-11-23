import logging
from typing import Optional, Tuple
from telegram import Update
from telegram.ext import ContextTypes

from app.db.repository import (
    get_credentials,
    upsert_user,
    save_chat_message,
    get_chat_history,
)
from app.bot.keyboards import (
    get_main_keyboard,
    get_task_actions_keyboard,
    get_connect_instance_keyboard,
)
from app.odoo.attendance_client import AttendanceOdooClient
from app.odoo.task_client import TaskOdooClient
from app.ai.agent_orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)


def get_user_main_keyboard(user_id: int):
    """Generates dynamic reply keyboard based on what the user actually connected."""
    creds = get_credentials(user_id) or {}
    has_att = bool(creds.get("att_odoo_url") and creds.get("att_odoo_key"))
    has_task = bool(creds.get("task_odoo_url") and creds.get("task_odoo_key"))
    return get_main_keyboard(has_attendance=has_att, has_tasks=has_task)


def get_clients_for_user(user_id: int) -> Tuple[Optional[AttendanceOdooClient], Optional[TaskOdooClient]]:
    """
    Dynamically loads Attendance and Task clients based on available credentials.
    Does NOT fail if only one of the two is configured.
    """
    creds = get_credentials(user_id)
    if not creds:
        return None, None

    att_client = None
    if creds.get("att_odoo_url") and creds.get("att_odoo_db") and creds.get("att_odoo_user") and creds.get("att_odoo_key"):
        try:
            att_client = AttendanceOdooClient(
                url=creds["att_odoo_url"],
                db=creds["att_odoo_db"],
                user=creds["att_odoo_user"],
                key=creds["att_odoo_key"]
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Attendance client for user {user_id}: {e}")

    task_client = None
    if creds.get("task_odoo_url") and creds.get("task_odoo_db") and creds.get("task_odoo_user") and creds.get("task_odoo_key"):
        try:
            task_client = TaskOdooClient(
                url=creds["task_odoo_url"],
                db=creds["task_odoo_db"],
                user=creds["task_odoo_user"],
                key=creds["task_odoo_key"]
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Task client for user {user_id}: {e}")

    return att_client, task_client


def escape_md(text: str) -> str:
    """Escapes markdown special characters so Telegram parser never breaks on task names."""
    if not text:
        return ""
    return str(text).replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "'")


async def safe_edit_text(message, text: str, **kwargs):
    """
    Safely edits a Telegram message.
    Tries Markdown first. If Telegram raises any entity parsing or formatting error,
    it cleanly falls back to plain text so the message is never lost!
    """
    try:
        return await message.edit_text(text, parse_mode="Markdown", **kwargs)
    except Exception as e:
        logger.warning(f"Telegram Markdown edit failed ({e}). Falling back to plain text.")
        try:
            return await message.edit_text(text, parse_mode=None, **kwargs)
        except Exception as e2:
            logger.error(f"Telegram plain text edit also failed: {e2}")
            # If payload exceeds Telegram limit (4096 chars), truncate
            if len(text) > 4000:
                text = text[:4000] + "\n\n... (truncated)"
            return await message.edit_text(text[:4096], parse_mode=None)


async def safe_reply_text(update: Update, text: str, **kwargs):
    """
    Safely sends a Telegram reply.
    Falls back to plain text if Markdown parsing fails.
    """
    try:
        return await update.message.reply_text(text, parse_mode="Markdown", **kwargs)
    except Exception as e:
        logger.warning(f"Telegram Markdown reply failed ({e}). Falling back to plain text.")
        try:
            return await update.message.reply_text(text, parse_mode=None, **kwargs)
        except Exception as e2:
            logger.error(f"Telegram plain text reply also failed: {e2}")
            if len(text) > 4000:
                text = text[:4000] + "\n\n... (truncated)"
            return await update.message.reply_text(text[:4096], parse_mode=None)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    upsert_user(user.id, user.username or "", user.full_name or "")
    att_client, task_client = get_clients_for_user(user.id)

    if not att_client and not task_client:
        text = (
            f"👋 Hello {user.first_name}!\n\n"
            "I am your autonomous **Odoo Task & Attendance Agent**.\n"
            "I can manage your Odoo instances directly from Telegram:\n"
            "• ⏱️ Clock In / Clock Out (HR Attendance)\n"
            "• 📋 Tasks & Timesheets (Projects & Work Logs)\n\n"
            "👉 Please type `/setup` to connect your instance(s)."
        )
        await safe_reply_text(update, text, reply_markup=get_user_main_keyboard(user.id))
    else:
        conns = []
        if att_client:
            conns.append(f"• ⏱️ HR Attendance: `{att_client.employee_name}`")
        if task_client:
            conns.append(f"• 📋 Tasks & Timesheets: `{task_client.user}`")

        conn_summary = "\n".join(conns)
        text = (
            f"👋 Welcome back, {user.first_name}!\n\n"
            f"**Connected Instances:**\n{conn_summary}\n\n"
            "What would you like to do today?"
        )
        await safe_reply_text(update, text, reply_markup=get_user_main_keyboard(user.id))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🤖 **Odoo Telegram Task Assistant Commands**\n\n"
        "**Quick Commands:**\n"
        "• `/tasks` - View your open project pipeline tasks\n"
        "• `/timesheets` - View today's logged hours\n"
        "• `/clockin` - Clock in to work\n"
        "• `/clockout` - Clock out and show shift summary\n"
        "• `/status` - Check current attendance state & connections\n"
        "• `/setup` - Configure, connect or update Odoo instances\n\n"
        "**Natural Language Queries & Actions:**\n"
        "• *'List my tasks'* or *'Show my pipeline tasks'*\n"
        "• *'Show my internal tasks'*\n"
        "• *'What tasks are assigned to Sarah?'*\n"
        "• *'Log 2 hours on task 42 fixed bug'*\n"
        "• *'Clock me in and show my top priority tasks'*"
    )
    await safe_reply_text(update, text, reply_markup=get_user_main_keyboard(update.effective_user.id))


async def clock_in_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    att_client, _ = get_clients_for_user(user_id)
    if not att_client:
        await update.message.reply_text(
            "⏱️ You haven't connected an HR Attendance instance yet.\n"
            "Would you like to connect it now?",
            reply_markup=get_connect_instance_keyboard("attendance")
        )
        return

    status_msg = await update.message.reply_text("⏳ Processing Clock-In...")
    res = att_client.clock_in()
    msg = res.get("message") or res.get("error") or "❌ Clock-in failed."
    await safe_edit_text(status_msg, msg)


async def clock_out_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    att_client, _ = get_clients_for_user(user_id)
    if not att_client:
        await update.message.reply_text(
            "⏱️ You haven't connected an HR Attendance instance yet.\n"
            "Would you like to connect it now?",
            reply_markup=get_connect_instance_keyboard("attendance")
        )
        return

    status_msg = await update.message.reply_text("⏳ Processing Clock-Out...")
    res = att_client.clock_out()
    msg = res.get("message") or res.get("error") or "❌ Clock-out failed."
    await safe_edit_text(status_msg, msg)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    att_client, task_client = get_clients_for_user(user_id)

    if not att_client and not task_client:
        await update.message.reply_text("⚠️ No Odoo instances connected. Please run /setup first.")
        return

    lines = ["📊 **System & Connection Status:**\n"]

    # Tasks status
    if task_client:
        lines.append(f"• 📋 **Tasks & Timesheets:** Connected as `{task_client.user}` ✅")
        lines.append(f"  URL: `{task_client.url}` | DB: `{task_client.db}`\n")
    else:
        lines.append("• 📋 **Tasks & Timesheets:** Not configured ⚪\n")

    # Attendance status
    if att_client:
        res = att_client.get_status()
        if res.get("is_clocked_in"):
            lines.append(
                f"• ⏱️ **Attendance:** Connected ✅\n"
                f"  Status: **Clocked IN**\n"
                f"  Check-in: `{res.get('check_in')}`\n"
                f"  Current Shift: `{res.get('current_session_hours')} hrs`\n"
                f"  Total Today: `{res.get('total_hours_today')} hrs`"
            )
        else:
            lines.append(
                f"• ⏱️ **Attendance:** Connected ✅\n"
                f"  Status: **Clocked OUT**\n"
                f"  Total Worked Today: `{res.get('total_hours_today', 0.0)} hrs`"
            )
    else:
        lines.append("• ⏱️ **Attendance:** Not configured ⚪")

    await safe_reply_text(update, "\n".join(lines), reply_markup=get_user_main_keyboard(user_id))


async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    _, task_client = get_clients_for_user(user_id)
    if not task_client:
        await update.message.reply_text(
            "📋 You haven't connected a Tasks & Timesheets instance yet.\n"
            "Would you like to connect it now?",
            reply_markup=get_connect_instance_keyboard("task")
        )
        return

    status_msg = await update.message.reply_text("🔍 Fetching your pipeline tasks...")
    tasks = task_client.search_tasks(my_tasks_only=True, open_only=True, limit=10)

    if not tasks:
        await safe_edit_text(status_msg, "🎉 You have no open tasks assigned in your pipeline!")
        return

    await status_msg.delete()

    # Build clean consolidated summary card
    lines = [f"📋 **Your Open Pipeline Tasks ({len(tasks)}):**\n"]
    for i, t in enumerate(tasks, 1):
        tid = t["id"]
        title = escape_md(t["name"])
        proj = escape_md(t.get("project") or "No Project")
        stage = escape_md(t.get("stage") or "Open")
        deadline = t.get("deadline") or "No deadline"
        lines.append(f"{i}. **#{tid}: {title}**\n   📁 Project: `{proj}` | 🏷️ `{stage}` | 📅 `{deadline}`")

    await safe_reply_text(update, "\n".join(lines), reply_markup=get_user_main_keyboard(user_id))

    # Send action buttons for top 3 tasks
    for t in tasks[:3]:
        tid = t["id"]
        title = t["name"][:35]
        await update.message.reply_text(
            f"Actions for #{tid}: {title}",
            reply_markup=get_task_actions_keyboard(tid)
        )


async def timesheet_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    _, task_client = get_clients_for_user(user_id)
    if not task_client:
        await update.message.reply_text(
            "📋 You haven't connected a Tasks & Timesheets instance yet.\n"
            "Would you like to connect it now?",
            reply_markup=get_connect_instance_keyboard("task")
        )
        return

    lines = task_client.get_today_timesheets()
    if not lines:
        await safe_reply_text(update, "⏳ No timesheets logged yet for today.", reply_markup=get_user_main_keyboard(user_id))
        return

    total = sum(l["hours"] for l in lines)
    out = [f"⏳ **Today's Timesheets (Total: {total:.2f}h):**\n"]
    for l in lines:
        tname = escape_md(l['task_name'])
        pname = escape_md(l['project_name'])
        desc = escape_md(l['description'])
        out.append(f"• **{l['hours']:.2f}h** on *{tname}* ({pname}): {desc}")

    await safe_reply_text(update, "\n".join(out), reply_markup=get_user_main_keyboard(user_id))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text.strip()
    user_kb = get_user_main_keyboard(user.id)

    # Fast short-circuit on button taps
    if text == "⏱️ Clock In":
        await clock_in_cmd(update, context)
        return
    elif text == "⏹️ Clock Out":
        await clock_out_cmd(update, context)
        return
    elif text in ("📋 My Tasks", "🔍 All Tasks"):
        await tasks_cmd(update, context)
        return
    elif text == "🔍 Search Tasks":
        await safe_reply_text(
            update,
            "🔍 **How to Search Tasks:**\n\n"
            "Just ask me in plain text! For example:\n"
            "• *'Show my open pipeline tasks'*\n"
            "• *'What tasks are assigned to Girija?'*\n"
            "• *'Show tasks in In Progress stage'*\n"
            "• *'Find tasks with keyword POS'*\n"
            "• *'List tasks in project SKIT'*",
            reply_markup=user_kb
        )
        return
    elif text in ("⏳ Today's Hours", "⏳ Attendance Hours"):
        await status_cmd(update, context)
        return
    elif text == "⏳ Today's Timesheets":
        await timesheet_cmd(update, context)
        return
    elif text in ("⏱️ Connect Clock-In", "⏱️ Connect Attendance"):
        from app.bot.handlers.setup_wizard import start_setup
        await start_setup(update, context)
        return
    elif text in ("📋 Connect Tasks", "⚙️ Setup Odoo"):
        from app.bot.handlers.setup_wizard import start_setup
        await start_setup(update, context)
        return
    elif text == "⚙️ Settings":
        await status_cmd(update, context)
        return
    elif text == "ℹ️ Help":
        await help_cmd(update, context)
        return
    elif text == "➕ Log Time":
        _, task_client = get_clients_for_user(user.id)
        if not task_client:
            await update.message.reply_text(
                "📋 You haven't connected a Tasks & Timesheets instance yet.",
                reply_markup=get_connect_instance_keyboard("task")
            )
            return
        await safe_reply_text(
            update,
            "To log time, tell me in plain text! For example:\n"
            "• *'Log 2 hours on task 45 worked on API'* \n"
            "• *'Log 1.5h on task 102 fixing login issue'* \n"
            "• *'Log 45 minutes on task 102 for yesterday'*",
            reply_markup=user_kb
        )
        return

    # Check if user has at least one instance configured
    att_client, task_client = get_clients_for_user(user.id)
    if not att_client and not task_client:
        await update.message.reply_text(
            "⚠️ You haven't connected any Odoo instances yet.\n"
            "Please send /setup to connect your instance!",
            parse_mode="Markdown"
        )
        return

    # Natural Language Agent Loop
    thinking_msg = await update.message.reply_text("💭 Thinking...")
    try:
        history = get_chat_history(user.id, limit=6)
        orchestrator = AgentOrchestrator(att_client, task_client)
        reply = orchestrator.run(user_message=text, history=history)

        save_chat_message(user.id, "user", text)
        save_chat_message(user.id, "assistant", reply)

        await safe_edit_text(thinking_msg, reply)
    except Exception as e:
        logger.exception("Agent execution failed")
        await safe_edit_text(thinking_msg, f"❌ An error occurred: {str(e)}")
