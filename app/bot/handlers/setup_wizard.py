import re
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from app.db.repository import save_credentials, upsert_user, get_credentials
from app.bot.keyboards import get_main_keyboard, get_instance_choice_keyboard
from app.odoo.base_client import clean_odoo_url
from app.odoo.attendance_client import AttendanceOdooClient
from app.odoo.task_client import TaskOdooClient

logger = logging.getLogger(__name__)

CHOOSING_MODE, AWAITING_SAME_CREDS, AWAITING_TASKS_CREDS, AWAITING_ATT_CREDS, AWAITING_SEPARATE_TASK_CREDS = range(5)


def strip_field(val: str, prefix_regex: str) -> str:
    """Strip list markers, labels, quotes, and whitespace from input fields."""
    val = (val or "").strip()
    val = re.sub(r"^\d+[\.\)]\s*", "", val).strip()   # Strip 1. or 1)
    val = re.sub(r"^[-*]\s*", "", val).strip()         # Strip bullet points - or *
    val = re.sub(prefix_regex, "", val, flags=re.IGNORECASE).strip()
    return val.strip("'\"")


def parse_credentials_text(text: str) -> tuple[str, str, str, str]:
    """
    Intelligently parses newline- or comma-separated credentials.
    Supports labeled inputs in any order or plain sequential lines.
    """
    raw_lines = [line.strip() for line in text.replace(",", "\n").split("\n") if line.strip()]

    # 1. Attempt labeled key-value extraction
    labeled = {}
    for line in raw_lines:
        m_url = re.match(r"^(?:url|instance|host|server)\s*[:=]\s*(.+)$", line, re.I)
        if m_url:
            labeled["url"] = m_url.group(1).strip()
            continue

        m_db = re.match(r"^(?:database\s*name|database|db)\s*[:=]\s*(.+)$", line, re.I)
        if m_db:
            labeled["db"] = m_db.group(1).strip()
            continue

        m_user = re.match(r"^(?:username|email|user|login)\s*[:=]\s*(.+)$", line, re.I)
        if m_user:
            labeled["user"] = m_user.group(1).strip()
            continue

        m_key = re.match(r"^(?:api\s*key|api-key|password|api_key|token|key)\s*[:=]\s*(.+)$", line, re.I)
        if m_key:
            labeled["key"] = m_key.group(1).strip()
            continue

    if len(labeled) == 4:
        url = clean_odoo_url(labeled["url"])
        db = strip_field(labeled["db"], r"^(?:database\s*name|database|db)\s*[:=]\s*")
        user = strip_field(labeled["user"], r"^(?:username|email|user|login)\s*[:=]\s*")
        key = strip_field(labeled["key"], r"^(?:api\s*key|api-key|password|api_key|token|key)\s*[:=]\s*")
        return url, db, user, key

    # 2. Sequential fallback
    if len(raw_lines) >= 4:
        url = clean_odoo_url(raw_lines[0])
        db = strip_field(raw_lines[1], r"^(?:database\s*name|database|db)\s*[:=]\s*")
        user = strip_field(raw_lines[2], r"^(?:username|email|user|login)\s*[:=]\s*")
        key = strip_field(raw_lines[3], r"^(?:api\s*key|api-key|password|api_key|token|key)\s*[:=]\s*")
        return url, db, user, key

    return "", "", "", ""


async def start_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Initiates the setup flow."""
    user = update.effective_user
    upsert_user(user.id, user.username or "", user.full_name or "")

    existing = get_credentials(user.id) or {}
    has_att = bool(existing.get("att_odoo_url"))
    has_task = bool(existing.get("task_odoo_url"))

    status_text = ""
    if has_att or has_task:
        status_text = (
            "📌 **Current Status:**\n"
            f"• Attendance Instance: {'✅ Connected' if has_att else '⚪ Not configured'}\n"
            f"• Tasks Instance: {'✅ Connected' if has_task else '⚪ Not configured'}\n\n"
        )

    text = (
        f"👋 Welcome {user.first_name}!\n\n"
        f"{status_text}"
        "Select what you would like to configure:"
    )

    if update.message:
        await update.message.reply_text(text, reply_markup=get_instance_choice_keyboard(), parse_mode="Markdown")
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=get_instance_choice_keyboard(), parse_mode="Markdown")

    return CHOOSING_MODE


async def mode_chosen_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    mode = query.data
    context.user_data["setup_mode"] = mode

    sample_block = (
        "Send your 4 connection values (one per line):\n\n"
        "```text\n"
        "https://skit-timesheet.odoo.com\n"
        "skit-timesheet\n"
        "your_email@company.com\n"
        "your_api_key_or_password\n"
        "```\n\n"
        "🔒 *Your message will be automatically deleted immediately after reading for security.*"
    )

    if mode == "setup_mode_same":
        prompt = f"✨ **All-in-One Configuration (Same Instance)**\n\n{sample_block}"
        await query.edit_message_text(prompt, parse_mode="Markdown")
        return AWAITING_SAME_CREDS

    elif mode == "setup_mode_tasks_only":
        prompt = f"📋 **Tasks & Timesheets Instance Setup**\n\n{sample_block}"
        await query.edit_message_text(prompt, parse_mode="Markdown")
        return AWAITING_TASKS_CREDS

    elif mode == "setup_mode_attendance_only":
        prompt = f"⏱️ **HR Attendance (Clock In/Out) Instance Setup**\n\n{sample_block}"
        await query.edit_message_text(prompt, parse_mode="Markdown")
        return AWAITING_ATT_CREDS

    elif mode == "setup_mode_separate":
        skip_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip Attendance", callback_data="skip_att_step")]])
        prompt = (
            "🔀 **Step 1 of 2: Attendance Instance**\n\n"
            "Please send the 4 values for your **Attendance Odoo** (or click Skip):\n\n"
            f"{sample_block}"
        )
        await query.edit_message_text(prompt, parse_mode="Markdown", reply_markup=skip_kb)
        return AWAITING_ATT_CREDS

    return CHOOSING_MODE


async def receive_same_creds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        await update.message.delete()
    except Exception:
        pass

    url, db, user, key = parse_credentials_text(text)
    if not all([url, db, user, key]):
        await update.effective_chat.send_message(
            "❌ Could not parse all 4 values. Please send:\n1. URL\n2. Database\n3. Username/Email\n4. API Key"
        )
        return AWAITING_SAME_CREDS

    status_msg = await update.effective_chat.send_message(f"⏳ Verifying connection to `{url}`...", parse_mode="Markdown")
    try:
        client = TaskOdooClient(url, db, user, key)
        test = client.test_connection()
        if not test.get("success"):
            raise ConnectionError(test.get("error", "Unknown error"))
    except Exception as e:
        await status_msg.edit_text(f"❌ **Connection failed:**\n`{str(e)}`\n\nPlease check your inputs and try again.", parse_mode="Markdown")
        return AWAITING_SAME_CREDS

    save_credentials(
        telegram_id=update.effective_user.id,
        same_instance=True,
        att_url=url, att_db=db, att_user=user, att_key=key,
        task_url=url, task_db=db, task_user=user, task_key=key
    )

    await status_msg.edit_text(
        f"✅ **All-in-One Setup Complete!**\n\n"
        f"Connected to `{url}` as `{user}`.\n"
        "Both Attendance (Clock In/Out) and Tasks & Timesheets are ready to use!",
        parse_mode="Markdown"
    )
    await update.effective_chat.send_message("Choose an action below:", reply_markup=get_main_keyboard(has_attendance=True, has_tasks=True))
    return ConversationHandler.END


async def receive_tasks_creds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        await update.message.delete()
    except Exception:
        pass

    url, db, user, key = parse_credentials_text(text)
    if not all([url, db, user, key]):
        await update.effective_chat.send_message(
            "❌ Could not parse all 4 values. Please send:\n1. URL\n2. Database\n3. Username/Email\n4. API Key"
        )
        return AWAITING_TASKS_CREDS

    status_msg = await update.effective_chat.send_message(f"⏳ Verifying Tasks connection to `{url}`...", parse_mode="Markdown")
    try:
        client = TaskOdooClient(url, db, user, key)
        test = client.test_connection()
        if not test.get("success"):
            raise ConnectionError(test.get("error", "Unknown error"))
    except Exception as e:
        await status_msg.edit_text(f"❌ **Connection failed:**\n`{str(e)}`\n\nPlease check your inputs and try again.", parse_mode="Markdown")
        return AWAITING_TASKS_CREDS

    save_credentials(
        telegram_id=update.effective_user.id,
        same_instance=False,
        task_url=url, task_db=db, task_user=user, task_key=key
    )

    await status_msg.edit_text(
        f"✅ **Tasks & Timesheets Connected!**\n\n"
        f"Connected to `{url}` as `{user}`.\n"
        "You can now view tasks, mark tasks done, and log timesheets directly from Telegram!",
        parse_mode="Markdown"
    )
    existing = get_credentials(update.effective_user.id) or {}
    has_att = bool(existing.get("att_odoo_url"))
    await update.effective_chat.send_message(
        "Choose an action below:",
        reply_markup=get_main_keyboard(has_attendance=has_att, has_tasks=True)
    )
    return ConversationHandler.END


async def receive_att_creds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        await update.message.delete()
    except Exception:
        pass

    url, db, user, key = parse_credentials_text(text)
    if not all([url, db, user, key]):
        await update.effective_chat.send_message(
            "❌ Could not parse all 4 values. Please send:\n1. URL\n2. Database\n3. Username/Email\n4. API Key"
        )
        return AWAITING_ATT_CREDS

    status_msg = await update.effective_chat.send_message(f"⏳ Verifying Attendance connection to `{url}`...", parse_mode="Markdown")
    try:
        client = AttendanceOdooClient(url, db, user, key)
        test = client.test_connection()
        if not test.get("success"):
            raise ConnectionError(test.get("error", "Unknown error"))
    except Exception as e:
        await status_msg.edit_text(f"❌ **Connection failed:**\n`{str(e)}`\n\nPlease check your inputs and try again.", parse_mode="Markdown")
        return AWAITING_ATT_CREDS

    mode = context.user_data.get("setup_mode", "setup_mode_attendance_only")

    if mode == "setup_mode_separate":
        context.user_data["temp_att_creds"] = (url, db, user, key)
        skip_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip Tasks", callback_data="skip_task_step")]])
        await status_msg.edit_text(
            "✅ Attendance instance verified!\n\n"
            "🔀 **Step 2 of 2: Tasks & Timesheets Instance**\n"
            "Now send the 4 values for your **Tasks & Timesheets Odoo** (or click Skip):",
            parse_mode="Markdown",
            reply_markup=skip_kb
        )
        return AWAITING_SEPARATE_TASK_CREDS
    else:
        save_credentials(
            telegram_id=update.effective_user.id,
            same_instance=False,
            att_url=url, att_db=db, att_user=user, att_key=key
        )
        existing = get_credentials(update.effective_user.id) or {}
        has_task = bool(existing.get("task_odoo_url"))
        await status_msg.edit_text(
            f"✅ **HR Attendance Connected!**\n\n"
            f"Connected to `{url}` as `{user}`.\n"
            "You can now Clock In, Clock Out, and track your work hours!",
            parse_mode="Markdown"
        )
        await update.effective_chat.send_message(
            "Choose an action below:",
            reply_markup=get_main_keyboard(has_attendance=True, has_tasks=has_task)
        )
        return ConversationHandler.END


async def skip_att_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    prompt = (
        "⏭️ Skipped Attendance instance.\n\n"
        "🔀 **Step 2: Tasks & Timesheets Instance**\n"
        "Please send the 4 connection values for your **Tasks & Timesheet Odoo**:"
    )
    await query.edit_message_text(prompt, parse_mode="Markdown")
    return AWAITING_SEPARATE_TASK_CREDS


async def skip_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    temp_att = context.user_data.get("temp_att_creds")
    if temp_att:
        url, db, user, key = temp_att
        save_credentials(
            telegram_id=update.effective_user.id,
            same_instance=False,
            att_url=url, att_db=db, att_user=user, att_key=key
        )

    await query.edit_message_text("✅ Attendance instance saved. Tasks setup skipped.", parse_mode="Markdown")
    await update.effective_chat.send_message(
        "Choose an action below:",
        reply_markup=get_main_keyboard(has_attendance=True, has_tasks=False)
    )
    return ConversationHandler.END


async def receive_separate_task_creds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    try:
        await update.message.delete()
    except Exception:
        pass

    url, db, user, key = parse_credentials_text(text)
    if not all([url, db, user, key]):
        await update.effective_chat.send_message(
            "❌ Could not parse all 4 values. Please send:\n1. URL\n2. Database\n3. Username/Email\n4. API Key"
        )
        return AWAITING_SEPARATE_TASK_CREDS

    status_msg = await update.effective_chat.send_message(f"⏳ Verifying Tasks connection to `{url}`...", parse_mode="Markdown")
    try:
        client = TaskOdooClient(url, db, user, key)
        test = client.test_connection()
        if not test.get("success"):
            raise ConnectionError(test.get("error", "Unknown error"))
    except Exception as e:
        await status_msg.edit_text(f"❌ **Connection failed:**\n`{str(e)}`\n\nPlease check your inputs and try again.", parse_mode="Markdown")
        return AWAITING_SEPARATE_TASK_CREDS

    temp_att = context.user_data.get("temp_att_creds")
    att_url = temp_att[0] if temp_att else ""
    att_db = temp_att[1] if temp_att else ""
    att_user = temp_att[2] if temp_att else ""
    att_key = temp_att[3] if temp_att else ""

    save_credentials(
        telegram_id=update.effective_user.id,
        same_instance=False,
        att_url=att_url, att_db=att_db, att_user=att_user, att_key=att_key,
        task_url=url, task_db=db, task_user=user, task_key=key
    )

    await status_msg.edit_text(
        "✅ **Separate Instances Connected Successfully!**\n\n"
        "• Instance 1: Attendance\n"
        "• Instance 2: Tasks & Timesheets\n\n"
        "You're all set!",
        parse_mode="Markdown"
    )
    await update.effective_chat.send_message(
        "Choose an action below:",
        reply_markup=get_main_keyboard(has_attendance=bool(att_url), has_tasks=True)
    )
    return ConversationHandler.END


async def cancel_setup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Setup cancelled. Type /setup to start again anytime.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


def get_setup_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("setup", start_setup),
            MessageHandler(filters.Regex("^⚙️ Settings$"), start_setup),
            CallbackQueryHandler(mode_chosen_callback, pattern="^setup_mode_")
        ],
        states={
            CHOOSING_MODE: [CallbackQueryHandler(mode_chosen_callback, pattern="^setup_mode_")],
            AWAITING_SAME_CREDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_same_creds)],
            AWAITING_TASKS_CREDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tasks_creds)],
            AWAITING_ATT_CREDS: [
                CallbackQueryHandler(skip_att_callback, pattern="^skip_att_step$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_att_creds)
            ],
            AWAITING_SEPARATE_TASK_CREDS: [
                CallbackQueryHandler(skip_task_callback, pattern="^skip_task_step$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_separate_task_creds)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_setup)],
        allow_reentry=True
    )
