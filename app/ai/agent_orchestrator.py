import json
import logging
from datetime import date
from typing import Dict, Any, List, Optional

from app.ai.llm_provider import llm_provider
from app.ai.tools_definitions import ATTENDANCE_TOOLS, TASK_TOOLS
from app.odoo.attendance_client import AttendanceOdooClient
from app.odoo.task_client import TaskOdooClient

logger = logging.getLogger(__name__)


def build_system_prompt(
    att_client: Optional[AttendanceOdooClient],
    task_client: Optional[TaskOdooClient]
) -> str:
    today_str = date.today().strftime("%Y-%m-%d")

    att_status = (
        f"CONNECTED (Employee: '{att_client.employee_name}')"
        if att_client
        else "NOT CONNECTED. If the user asks for clock-in/out or attendance, inform them to connect their Attendance instance via /setup."
    )

    task_status = (
        f"CONNECTED (User: '{task_client.user}')"
        if task_client
        else "NOT CONNECTED. If the user asks for tasks or timesheets, inform them to connect their Tasks instance via /setup."
    )

    return (
        f"You are the autonomous Odoo Telegram Assistant.\n"
        f"Today is {today_str}.\n\n"
        f"Connected Services:\n"
        f"• HR Attendance Instance: {att_status}\n"
        f"• Tasks & Timesheets Instance: {task_status}\n\n"
        f"Your Capabilities & Guidelines:\n"
        f"1. HR Attendance: When connected, handle clock-in, clock-out, active shift status, and daily hours worked.\n"
        f"2. Tasks & Pipeline: When connected, search tasks for the user OR for any colleague/team member (e.g. 'Girija', 'Guna', 'Arthi').\n"
        f"   - Internal Tasks vs Pipeline Tasks:\n"
        f"     • 'Internal Tasks': In this organization, Internal Tasks specifically refers to tasks in the project named 'Internal' (e.g. #197 Time Off, meetings, training, non-client internal tasks).\n"
        f"     • 'Pipeline Tasks' / 'My Pipeline': Refers to the user's active development pipeline across all their client and development projects (OCA, Zoho, Real Estate, etc.) across open stages.\n"
        f"     • NEVER label client development tasks as 'Internal tasks'! Their stage on the UI is 'Pipeline', and their projects are their actual projects.\n"
        f"   - If user asks for general tasks ('my tasks', 'my pipeline', 'all open tasks'): call `search_tasks(my_tasks_only=True, open_only=True)` with stage_name empty.\n"
        f"   - If user asks for internal tasks ('my internal tasks', 'internal tasks'): search with project_name='Internal'.\n"
        f"   - If user asks for a specific stage ('my todo tasks', 'in progress tasks', 'done tasks', 'on hold tasks'): call `search_tasks(my_tasks_only=True, stage_name='<Stage>')`.\n"
        f"   - Multi-Stage Queries: If user asks for multiple stages (e.g. 'internal and onhold', 'pipeline and on hold'), group tasks under separate headers for each stage based on their actual returned `stage` property. NEVER duplicate or repeat tasks across stages!\n"
        f"   - If a specific stage query returns 0 tasks, report honestly: 'You currently have no tasks in the <Stage> stage.' Mention what stages their open tasks are in.\n"
        f"   - When user asks about a team member/colleague: call `search_tasks(assignee_name=colleague_name, open_only=True)`.\n"
        f"   - When user asks for completed/done tasks: call `search_tasks(open_only=False, stage_name='Done')`.\n"
        f"3. Task Updates: When user asks to change, move, or update a task (e.g. 'move task 28926 to in progress', 'set priority of 28926 to high', 'change deadline to Friday', 'assign 28926 to Mohanraj'): call `update_task(task_id=..., ...)`.\n"
        f"4. Timesheets: When connected, log worked hours on specific tasks (`log_timesheet`), view today's timesheet logs (`get_today_timesheets`).\n"
        f"5. Compound requests: For example, sequentially execute timesheet logging, task completion, and clock-out.\n"
        f"6. If a requested feature's instance is NOT connected, explain politely how to configure or connect it.\n\n"
        f"Formatting & Presentation Guidelines for Telegram:\n"
        f"- Format every task item uniformly:\n"
        f"  <number>. #<id>: <Task Name> | 📁 <Project Name> | 🏷️ Stage: <Stage Name>\n"
        f"- NEVER output web links or URLs (do NOT write [Title](https://...)).\n"
        f"- Do NOT invent or alter task names or project names.\n"
        f"- DO NOT use markdown table syntax (|---|---|).\n"
        f"- Always be concise, polite, and helpful."
    )


class AgentOrchestrator:
    def __init__(
        self,
        att_client: Optional[AttendanceOdooClient],
        task_client: Optional[TaskOdooClient]
    ):
        self.att_client = att_client
        self.task_client = task_client

        # Register tools dynamically based on which clients are connected
        self.active_tools = []
        self._dispatch_map = {}

        if self.att_client:
            self.active_tools.extend(ATTENDANCE_TOOLS)
            self._dispatch_map.update({
                "clock_in": lambda args: self.att_client.clock_in(),
                "clock_out": lambda args: self.att_client.clock_out(),
                "get_attendance_status": lambda args: self.att_client.get_status(),
                "get_daily_attendance_summary": lambda args: self.att_client.get_today_summary(),
            })

        if self.task_client:
            self.active_tools.extend(TASK_TOOLS)
            self._dispatch_map.update({
                "search_tasks": lambda args: self.task_client.search_tasks(**args),
                "find_team_members": lambda args: self.task_client.find_users(**args),
                "create_task": lambda args: self.task_client.create_task(**args),
                "complete_task": lambda args: self.task_client.complete_task(**args),
                "update_task": lambda args: self.task_client.update_task(**args),
                "log_timesheet": lambda args: self.task_client.log_timesheet(**args),
                "get_today_timesheets": lambda args: self.task_client.get_today_timesheets(**args),
            })

    def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        handler = self._dispatch_map.get(tool_name)
        if not handler:
            return {"error": f"Tool '{tool_name}' is not available because the required Odoo instance is not connected. User can connect it via /setup."}
        try:
            return handler(args)
        except Exception as e:
            logger.exception(f"Error executing tool {tool_name}")
            return {"error": str(e)}

    def _retrieve_rag_context(self, user_message: str) -> Optional[str]:
        """
        RAG / Grounding Engine:
        Pre-retrieves live database records from Odoo for query requests (e.g. listing tasks,
        checking attendance, viewing timesheets). This guarantees ground truth in the prompt
        so the LLM never hallucinates or duplicates tasks across stages.
        """
        if not self.task_client and not self.att_client:
            return None

        import re
        msg_low = user_message.lower().strip()

        # Pure action commands (e.g. "move task 123", "log 2 hours") should use tools directly
        is_pure_write = any(msg_low.startswith(w) for w in ["move ", "set ", "change ", "update ", "create ", "add ", "log ", "clock "])
        if is_pure_write and not any(w in msg_low for w in ["list", "show", "what", "display", "get", "find"]):
            return None

        rag_parts = []

        # 1. Tasks RAG
        if self.task_client:
            task_keywords = ["task", "tasks", "pipeline", "todo", "to do", "stage", "stages", "working on", "assigned"]
            if any(w in msg_low for w in task_keywords):
                # Check if user specifically asks for "internal tasks" (referring to Project "Internal")
                is_internal_proj = bool(re.search(r'\binternal\s+tasks?\b|\btasks?\s+in\s+internal\b|\bproject\s+internal\b', msg_low))
                proj_name = "Internal" if is_internal_proj else None

                known_stages = {
                    "on hold": "On Hold", "onhold": "On Hold", "hold": "On Hold",
                    "in progress": "In Progress", "inprogress": "In Progress", "progress": "In Progress", "wip": "In Progress",
                    "to do": "To Do", "todo": "To Do",
                    "pipeline stage": "Pipeline",
                    "done": "Done", "completed": "Done", "closed": "Done",
                    "review": "Review", "code review": "Review",
                    "client validation": "Client Validation",
                    "devops": "Devops",
                    "testing": "Testing", "developer testing": "Developer Testing", "fc testing": "FC Testing", "final testing": "Final Testing"
                }

                matched_stages = []
                if not is_internal_proj:
                    for k, v in known_stages.items():
                        if re.search(r'\b' + re.escape(k) + r'\b', msg_low):
                            if v not in matched_stages:
                                matched_stages.append(v)

                stage_query = " and ".join(matched_stages) if matched_stages else None

                # Detect colleague
                colleague = None
                assignee_match = re.search(r'(?:assigned to|for|of)\s+([a-zA-Z]+)', msg_low)
                if assignee_match:
                    cand = assignee_match.group(1).strip()
                    if cand not in ("me", "my", "myself", "all", "tasks", "pipeline", "the", "stage", "internal"):
                        colleague = cand

                is_my = not colleague
                is_closed_query = any(s == "Done" for s in matched_stages)

                try:
                    tasks = self.task_client.search_tasks(
                        name=None,
                        project_name=proj_name,
                        stage_name=stage_query,
                        assignee_name=colleague,
                        my_tasks_only=is_my,
                        open_only=not is_closed_query,
                        limit=50
                    )
                    if tasks:
                        t_lines = [f"[ODOO LIVE DATABASE RETRIEVAL - {len(tasks)} REAL TASKS]:"]
                        for t in tasks:
                            t_lines.append(f"• #{t['id']}: {t['name']} | Project: {t['project']} | Stage: {t['stage']} | Priority: {t['priority']} | Deadline: {t['deadline']}")
                        t_lines.append("CRITICAL: Present ONLY these tasks grouped by their exact 'Stage' above. Do not invent or duplicate any tasks.")
                        rag_parts.append("\n".join(t_lines))
                    elif stage_query:
                        rag_parts.append(f"[ODOO LIVE DATABASE RETRIEVAL]: 0 tasks found for stage(s) '{stage_query}'.")
                    elif proj_name:
                        rag_parts.append(f"[ODOO LIVE DATABASE RETRIEVAL]: 0 tasks found in Project '{proj_name}'.")
                except Exception as e:
                    logger.warning(f"RAG task retrieval failed: {e}")

        # 2. Timesheets RAG
        if self.task_client and any(w in msg_low for w in ["timesheet", "timesheets", "logged today", "today's logs"]):
            try:
                logs = self.task_client.get_today_timesheets()
                if logs:
                    ts_lines = ["[ODOO LIVE DATABASE RETRIEVAL - TODAY'S TIMESHEETS]:"]
                    for l in logs:
                        ts_lines.append(f"• {l['hours']:.2f}h on Task #{l['task_id']} ({l['task_name']}): {l['description']}")
                    rag_parts.append("\n".join(ts_lines))
                else:
                    rag_parts.append("[ODOO LIVE DATABASE RETRIEVAL]: No timesheets logged for today.")
            except Exception as e:
                logger.warning(f"RAG timesheet retrieval failed: {e}")

        # 3. Attendance RAG
        if self.att_client and any(w in msg_low for w in ["attendance", "clocked in", "shift", "check-in status"]):
            try:
                status = self.att_client.get_status()
                rag_parts.append(f"[ODOO LIVE DATABASE RETRIEVAL - ATTENDANCE]: Checked in: {status['is_checked_in']}, Shift duration: {status['shift_duration']}, Today total: {status['today_hours']}")
            except Exception as e:
                logger.warning(f"RAG attendance retrieval failed: {e}")

        return "\n\n".join(rag_parts) if rag_parts else None

    def run(self, user_message: str, history: List[Dict[str, str]] = None) -> str:
        """Runs the agent loop with multi-provider failover, RAG grounding, and tool execution."""
        system_prompt = build_system_prompt(self.att_client, self.task_client)

        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)

        # Inject RAG context if applicable
        rag_context = self._retrieve_rag_context(user_message)
        if rag_context:
            messages.append({"role": "system", "content": rag_context})

        messages.append({"role": "user", "content": user_message})

        tools_param = self.active_tools if self.active_tools else None

        max_iterations = 5
        for _ in range(max_iterations):
            response = llm_provider.chat_completion(
                messages=messages,
                tools=tools_param,
                tool_choice="auto" if tools_param else None,
                temperature=0.2
            )

            choice = response.choices[0]
            msg = choice.message

            # Check if model wants to call tools
            if msg.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in msg.tool_calls
                    ]
                })

                for tc in msg.tool_calls:
                    fname = tc.function.name
                    fargs = {}
                    try:
                        fargs = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        pass

                    result = self.execute_tool(fname, fargs)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result)
                    })
            else:
                return msg.content or "Done."

        return "I processed your request, but hit the step limit."
