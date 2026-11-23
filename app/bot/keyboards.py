from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def get_main_keyboard(has_attendance: bool = True, has_tasks: bool = True) -> ReplyKeyboardMarkup:
    """Persistent reply keyboard with quick actions dynamically adjusted to connected instances."""
    if has_attendance and has_tasks:
        # Both instances connected: show all attendance, task, and timesheet buttons
        keyboard = [
            [KeyboardButton("⏱️ Clock In"), KeyboardButton("⏹️ Clock Out")],
            [KeyboardButton("📋 My Tasks"), KeyboardButton("⏳ Today's Timesheets")],
            [KeyboardButton("➕ Log Time"), KeyboardButton("⏳ Attendance Hours")],
            [KeyboardButton("🔍 Search Tasks"), KeyboardButton("⚙️ Settings")],
        ]
    elif has_tasks and not has_attendance:
        # Tasks instance only: show all task/timesheet buttons + prompt to connect attendance
        keyboard = [
            [KeyboardButton("📋 My Tasks"), KeyboardButton("⏳ Today's Timesheets")],
            [KeyboardButton("➕ Log Time"), KeyboardButton("🔍 Search Tasks")],
            [KeyboardButton("⏱️ Connect Attendance"), KeyboardButton("⚙️ Settings")],
        ]
    elif has_attendance and not has_tasks:
        # Attendance instance only: show clock in/out, hours + prompt to connect tasks
        keyboard = [
            [KeyboardButton("⏱️ Clock In"), KeyboardButton("⏹️ Clock Out")],
            [KeyboardButton("⏳ Attendance Hours"), KeyboardButton("📋 Connect Tasks")],
            [KeyboardButton("⚙️ Settings")],
        ]
    else:
        # Neither connected
        keyboard = [
            [KeyboardButton("⚙️ Setup Odoo"), KeyboardButton("ℹ️ Help")],
        ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_instance_choice_keyboard() -> InlineKeyboardMarkup:
    """Setup choices: Same instance, Tasks only, Attendance only, or Separate instances."""
    keyboard = [
        [
            InlineKeyboardButton("✨ All-in-One (Same Instance)", callback_data="setup_mode_same"),
        ],
        [
            InlineKeyboardButton("📋 Tasks & Timesheets Only", callback_data="setup_mode_tasks_only"),
            InlineKeyboardButton("⏱️ HR Attendance Only", callback_data="setup_mode_attendance_only"),
        ],
        [
            InlineKeyboardButton("🔀 Separate Instances (Two URLs)", callback_data="setup_mode_separate"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_task_actions_keyboard(task_id: int) -> InlineKeyboardMarkup:
    """Inline buttons attached to a specific task card."""
    keyboard = [
        [
            InlineKeyboardButton("⏱️ Log 1h", callback_data=f"quicklog_{task_id}_1.0"),
            InlineKeyboardButton("⏱️ Log 2h", callback_data=f"quicklog_{task_id}_2.0"),
            InlineKeyboardButton("✅ Mark Done", callback_data=f"complete_{task_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_connect_instance_keyboard(instance_type: str) -> InlineKeyboardMarkup:
    """Inline prompt button when user attempts an action for an unconfigured instance."""
    if instance_type == "attendance":
        btn = InlineKeyboardButton("⏱️ Connect Attendance Instance", callback_data="setup_mode_attendance_only")
    else:
        btn = InlineKeyboardButton("📋 Connect Tasks Instance", callback_data="setup_mode_tasks_only")
    return InlineKeyboardMarkup([[btn]])
