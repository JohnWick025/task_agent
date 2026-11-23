"""
OpenAI-compatible Tool Definitions for Multi-Provider LLMs & Agent Orchestration.
"""

ATTENDANCE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "clock_in",
            "description": "Clock in the user to start their work day/shift on the HR Attendance instance.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "clock_out",
            "description": "Clock out the user from their current active work day/shift.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_attendance_status",
            "description": "Check whether user is currently clocked in, current shift duration, and total hours worked today.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_daily_attendance_summary",
            "description": "Get detailed summary of all check-in and check-out sessions for today.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]

TASK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "Search and list project tasks with flexible filters. Can search for the current user ('me'), a specific team member by name, by stage (e.g. 'To Do', 'In Progress'), by project, or across the whole pipeline.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Keyword to match in task title/name."
                    },
                    "assignee_name": {
                        "type": "string",
                        "description": "Filter by assignee. Use 'me' or 'my' for the current user's tasks, or pass a colleague/team member's name (e.g. 'Girija', 'Guna', 'Arthi', 'Latha') to find tasks assigned to that person."
                    },
                    "my_tasks_only": {
                        "type": "boolean",
                        "description": "Set to true if user asks for their own tasks ('my tasks', 'my to-do tasks', 'my pipeline', 'assigned to me')."
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Filter by project name (e.g. 'Internal', 'Mobile App', 'SKIT')."
                    },
                    "stage_name": {
                        "type": "string",
                        "description": "Filter by Kanban stage name. Supports single stages (e.g. 'In Progress', 'Done', 'Review') or multiple combined stages (e.g. 'on hold and in progress', 'internal and on hold'). NOTE: If user asks for general pipeline tasks, leave stage_name empty."
                    },
                    "open_only": {
                        "type": "boolean",
                        "description": "Default is true. Returns open/active/pending pipeline tasks. Set to false ONLY if user explicitly asks for completed, closed, or done tasks."
                    },
                    "overdue": {
                        "type": "boolean",
                        "description": "If true, returns only tasks past their deadline."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return (default: 50)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_team_members",
            "description": "Search active team members or colleagues in Odoo to get their names and details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional name filter (e.g. 'Sarah', 'Alex')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new project task in Odoo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Title of the task"},
                    "project_name": {"type": "string", "description": "Target project name"},
                    "deadline": {"type": "string", "description": "Deadline in YYYY-MM-DD format"},
                    "description": {"type": "string", "description": "Task description"},
                    "allocated_hours": {"type": "number", "description": "Estimated / allocated hours"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as completed by moving it to the Done/closed stage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "The Odoo Task ID to complete"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Update any property of an existing task in Odoo: move stage (e.g. 'In Progress', 'On Hold', 'Review', 'Internal', 'Done'), set priority ('high' or 'normal'), set deadline, change allocated hours, assign to colleague, or update title/description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "The Odoo Task ID to update"},
                    "stage_name": {"type": "string", "description": "Target stage name (e.g. 'In Progress', 'On Hold', 'To Do', 'Internal', 'Review', 'Done')"},
                    "priority": {"type": "string", "description": "Priority: 'high' or 'normal'"},
                    "deadline": {"type": "string", "description": "Deadline in YYYY-MM-DD or relative like 'today', 'tomorrow'"},
                    "allocated_hours": {"type": "number", "description": "Estimated or allocated hours"},
                    "assignee_name": {"type": "string", "description": "Colleague name to assign the task to (or 'me')"},
                    "name": {"type": "string", "description": "New task title"},
                    "description": {"type": "string", "description": "New task description"}
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "log_timesheet",
            "description": "Log worked hours against a specific project task into analytic lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "The Odoo Task ID"
                    },
                    "hours": {
                        "type": "number",
                        "description": "Duration in hours (e.g. 1.5, 2.0, 0.75, or fractional hours)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Summary of work done (e.g. 'Fixed authentication bug')"
                    },
                    "date_str": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (e.g. '2026-11-19'). Defaults to today if omitted."
                    }
                },
                "required": ["task_id", "hours"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_timesheets",
            "description": "List all timesheet entries logged by user today (or for a given date).",
            "parameters": {
                "type": "object",
                "properties": {
                    "target_date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (defaults to today)"
                    }
                },
                "required": []
            }
        }
    }
]

ALL_TOOLS = ATTENDANCE_TOOLS + TASK_TOOLS
