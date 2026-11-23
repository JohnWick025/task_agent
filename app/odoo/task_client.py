import re
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional
from app.odoo.base_client import BaseOdooClient


class TaskOdooClient(BaseOdooClient):
    """Client for managing Projects, Tasks, and Timesheets in Odoo."""

    def __init__(self, url: str, db: str, user: str, key: str):
        super().__init__(url, db, user, key)
        fields = self.call("project.task", "fields_get", [], {"attributes": ["type"]})
        self.multi_assignee = "user_ids" in fields  # Odoo 17+ uses user_ids, older uses user_id
        self.has_state = "state" in fields          # Odoo 17+ task state (01_in_progress, 1_done, etc.)
        self.has_is_closed = "is_closed" in fields  # Odoo 17+ is_closed boolean flag
        self.has_active = "active" in fields        # active archive flag
        self._user_cache: Dict[int, str] = {}
        self._employee_id: Optional[int] = None

    def task_link(self, task_id: int) -> str:
        return f"{self.url}/web#id={task_id}&model=project.task&view_type=form"

    # ---------------------------------------------------------------- Users & Projects Lookup
    def find_users(self, name: str = "") -> List[Dict[str, Any]]:
        """Search active internal users in Odoo."""
        domain = [("share", "=", False), ("active", "=", True)]
        if name:
            domain.append(("name", "ilike", name.strip()))
        users = self.call(
            "res.users", "search_read", [domain],
            {"fields": ["id", "name", "email"], "limit": 30, "order": "name"}
        )
        for u in users:
            self._user_cache[u["id"]] = u["name"]
        return users

    def find_projects(self, name: str = "", limit: int = 30) -> List[Dict[str, Any]]:
        """Search projects in Odoo."""
        domain = [[("name", "ilike", name.strip())]] if name else [[]]
        return self.call(
            "project.project", "search_read", domain,
            {"fields": ["id", "name"], "limit": limit, "order": "id desc"}
        )

    def _resolve_employee_id(self) -> Optional[int]:
        """Resolve hr.employee linked to current user for timesheet tracking."""
        if self._employee_id is not None:
            return self._employee_id
        try:
            emps = self.call(
                "hr.employee", "search_read",
                [[("user_id", "=", self.uid)]],
                {"fields": ["id"], "limit": 1}
            )
            self._employee_id = emps[0]["id"] if emps else False
        except Exception:
            self._employee_id = False
        return self._employee_id

    # ---------------------------------------------------------------- Formatting Helpers
    @staticmethod
    def parse_hours(val: Any) -> float:
        """Parses various hour representations (e.g., 1.5, '1:30', '90m', '2 hours', '1,5') into decimal float."""
        if val is None:
            return 1.0
        if isinstance(val, (int, float)):
            return round(float(val), 2)

        s = str(val).strip().replace(",", ".")

        # HH:MM format like "01:30" or "2:45"
        if ":" in s:
            parts = s.split(":")
            if len(parts) == 2:
                try:
                    hours = int(parts[0].strip())
                    minutes = int(parts[1].strip())
                    return round(hours + (minutes / 60.0), 2)
                except Exception:
                    pass

        # String with hours/minutes like "1h 30m" or "45 mins" or "2 hrs"
        m_mins = re.search(r"(\d+(?:\.\d+)?)\s*(?:mins?|minutes?|m\b)", s, re.I)
        m_hrs = re.search(r"(\d+(?:\.\d+)?)\s*(?:hrs?|hours?|h\b)", s, re.I)
        if m_hrs or m_mins:
            total = 0.0
            if m_hrs:
                total += float(m_hrs.group(1))
            if m_mins:
                total += float(m_mins.group(1)) / 60.0
            return round(total, 2)

        # Plain number string e.g. "2.5" or "1.5"
        clean = re.sub(r"[^\d.]", "", s)
        try:
            return round(float(clean), 2)
        except Exception:
            return 1.0

    @staticmethod
    def parse_date(val: Any) -> str:
        """Normalizes date input into YYYY-MM-DD format."""
        if not val or str(val).lower() in ("today", "now", "current"):
            return date.today().isoformat()
        if str(val).lower() == "yesterday":
            return (date.today() - timedelta(days=1)).isoformat()

        s = str(val).strip()
        # Already YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            return s
        # DD/MM/YYYY or DD-MM-YYYY
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
        if m:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            return f"{y}-{int(mo):02d}-{int(d):02d}"
        # YYYY/MM/DD
        m2 = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
        if m2:
            y, mo, d = m2.group(1), m2.group(2), m2.group(3)
            return f"{y}-{int(mo):02d}-{int(d):02d}"

        return date.today().isoformat()

    # ---------------------------------------------------------------- Task Field Extraction
    def _task_fields(self) -> List[str]:
        fields = [
            "id", "name", "project_id", "stage_id", "date_deadline",
            "priority", "description", "parent_id", "tag_ids",
            "allocated_hours", "effective_hours",
        ]
        fields.append("user_ids" if self.multi_assignee else "user_id")
        return fields

    def _enrich_task(self, t: dict) -> dict:
        stage_name = t["stage_id"][1] if t.get("stage_id") else "Open"
        stage_id_val = t["stage_id"][0] if t.get("stage_id") else None

        # In this Odoo instance, Stage ID 1 and 170 are technically named 'Internal' in the backend database,
        # but are rendered on the UI statusbar and saved filters as 'Pipeline' ('Pipline').
        if stage_id_val in (1, 170) or (stage_name and stage_name.lower() == "internal"):
            stage_display = "Pipeline"
        else:
            stage_display = stage_name

        item = {
            "id": t["id"],
            "name": t["name"],
            "project": t["project_id"][1] if t.get("project_id") else "No Project",
            "project_id": t["project_id"][0] if t.get("project_id") else None,
            "deadline": str(t.get("date_deadline") or "") or "No deadline",
            "priority": "high" if str(t.get("priority")) == "1" else "normal",
            "stage": stage_display,
            "stage_id": stage_id_val,
            "description": (t.get("description") or "")[:300],
            "allocated_hours": t.get("allocated_hours") or 0.0,
            "effective_hours": t.get("effective_hours") or 0.0,
        }

        # Resolve human-readable assignee names
        if self.multi_assignee:
            uids = t.get("user_ids") or []
            item["assignee_ids"] = uids

            # Lazily populate cache for any unknown UIDs
            missing = [uid for uid in uids if uid not in self._user_cache and uid != self.uid]
            if missing:
                try:
                    fetched = self.call(
                        "res.users", "search_read",
                        [[("id", "in", missing)]],
                        {"fields": ["id", "name"]}
                    )
                    for fu in fetched:
                        self._user_cache[fu["id"]] = fu["name"]
                except Exception:
                    pass

            assignee_names = []
            for uid in uids:
                if uid in self._user_cache:
                    assignee_names.append(self._user_cache[uid])
                elif uid == self.uid:
                    assignee_names.append(self.user)
                else:
                    assignee_names.append(f"User #{uid}")
            item["assignees"] = assignee_names if assignee_names else ["Unassigned"]
        else:
            if t.get("user_id"):
                item["assignee_ids"] = [t["user_id"][0]]
                item["assignees"] = [t["user_id"][1]]
            else:
                item["assignee_ids"] = []
                item["assignees"] = ["Unassigned"]

        return item

    # ---------------------------------------------------------------- Search Tasks
    def search_tasks(
        self,
        name: str = None,
        project_name: str = None,
        stage_name: str = None,
        assignee_name: str = None,
        my_tasks_only: bool = False,
        open_only: bool = True,
        overdue: bool = False,
        limit: int = 50,
    ) -> List[dict]:
        """
        Flexible and accurate task search supporting:
        - Own tasks ('my tasks', 'my pipeline', 'my to do tasks')
        - Specific team members (by colleague name)
        - Specific stages (e.g., 'To Do', 'In Progress', 'Done')
        - Full open pipeline across all active stages
        """
        domain = []

        # 1. Active filter
        if self.has_active:
            domain.append(("active", "=", True))

        # 2. Assignee Resolution
        target_uid = None
        if my_tasks_only or (assignee_name and assignee_name.lower().strip() in ("me", "my", "myself", "self", "i")):
            target_uid = self.uid
        elif assignee_name and assignee_name.lower().strip() not in ("all", "everyone", "team", "anybody"):
            users = self.find_users(assignee_name)
            if users:
                target_uid = users[0]["id"]
            else:
                # If specific user ID not resolved by res.users, search on user name directly
                if self.multi_assignee:
                    domain.append(("user_ids.name", "ilike", assignee_name.strip()))
                else:
                    domain.append(("user_id.name", "ilike", assignee_name.strip()))

        if target_uid is not None:
            if self.multi_assignee:
                domain.append(("user_ids", "in", [target_uid]))
            else:
                domain.append(("user_id", "=", target_uid))

        # 3. Project Resolution
        if project_name:
            projs = self.find_projects(project_name, limit=1)
            if projs:
                domain.append(("project_id", "=", projs[0]["id"]))
            else:
                domain.append(("project_id.name", "ilike", project_name.strip()))

        # 4. Stage and Open/Closed State Resolution
        st_clean = stage_name.lower().strip() if stage_name else ""
        is_asking_closed = st_clean in ("done", "completed", "closed", "cancelled", "canceled") or (open_only is False)
        # General pipeline = entire active backlog/workflow across all open stages
        is_general_pipeline = not st_clean or st_clean in ("pipeline", "my pipeline", "open", "all open", "active", "pending", "all")

        if is_asking_closed:
            # User explicitly wants closed / done / completed tasks
            if self.has_state:
                domain.append(("state", "in", ["1_done", "1_canceled"]))
            elif self.has_is_closed:
                domain.append(("is_closed", "=", True))
            else:
                domain.append(("stage_id.name", "ilike", "Done"))
        elif st_clean and not is_general_pipeline:
            # Support single or compound stages (e.g. 'internal and onhold', 'to do', 'pipeline stage')
            stage_parts = [p.strip() for p in re.split(r",|\band\b|\b&\b", st_clean) if p.strip()]
            matched_stage_ids = set()
            for part in stage_parts:
                if part in ("internal", "internal stage", "pipeline stage", "pipline stage", "pipline"):
                    matched_stage_ids.update([1, 170])
                elif part in ("on hold", "onhold", "hold"):
                    matched_stage_ids.add(11)
                elif part in ("to do", "todo"):
                    matched_stage_ids.add(9)
                elif part in ("in progress", "progress", "wip"):
                    matched_stage_ids.add(10)
                elif part in ("review", "code review"):
                    matched_stage_ids.add(286)
                elif part in ("client validation", "validation"):
                    matched_stage_ids.add(270)
                else:
                    # Dynamically look up any custom stage by name
                    try:
                        found = self.call("project.task.type", "search_read", [[("name", "ilike", part)]], {"fields": ["id"]})
                        for fs in found:
                            matched_stage_ids.add(fs["id"])
                    except Exception:
                        pass

            if matched_stage_ids:
                domain.append(("stage_id", "in", list(matched_stage_ids)))
            else:
                domain.append(("stage_id.name", "ilike", stage_name.strip()))

            if self.has_is_closed:
                domain.append(("is_closed", "=", False))
            if self.has_state:
                domain.append(("state", "not in", ["1_done", "1_canceled"]))
        else:
            # Default: all open pipeline tasks across active stages
            if self.has_is_closed:
                domain.append(("is_closed", "=", False))
            if self.has_state:
                domain.append(("state", "not in", ["1_done", "1_canceled"]))
            domain.append(("stage_id.name", "not in", ["Done", "Cancelled", "Closed"]))

        # 5. Keyword filter
        if name:
            domain.append(("name", "ilike", name.strip()))

        # 6. Overdue filter
        if overdue:
            domain.append(("date_deadline", "<", date.today().isoformat()))
            domain.append(("date_deadline", "!=", False))

        raw_tasks = self.call(
            "project.task", "search_read", [domain],
            {
                "fields": self._task_fields(),
                "limit": min(limit, 50),
                "order": "id desc"
            }
        )

        return [self._enrich_task(t) for t in raw_tasks]

    def get_task(self, task_id: int) -> Optional[dict]:
        rows = self.call("project.task", "read", [[task_id]], {"fields": self._task_fields()})
        if not rows:
            return None
        return self._enrich_task(rows[0])

    def create_task(
        self,
        name: str,
        project_id: int = None,
        project_name: str = None,
        stage_name: str = None,
        deadline: str = None,
        description: str = "",
        allocated_hours: float = None,
    ) -> dict:
        vals = {"name": name, "description": description or ""}

        if project_name and not project_id:
            projs = self.find_projects(project_name, limit=1)
            if projs:
                project_id = projs[0]["id"]

        if project_id:
            vals["project_id"] = project_id

        # Assign to self by default
        if self.multi_assignee:
            vals["user_ids"] = [(6, 0, [self.uid])]
        else:
            vals["user_id"] = self.uid

        if deadline:
            vals["date_deadline"] = self.parse_date(deadline)
        if allocated_hours is not None:
            vals["allocated_hours"] = self.parse_hours(allocated_hours)

        task_id = self.call("project.task", "create", [vals])
        return {
            "task_id": task_id,
            "name": name,
            "url": self.task_link(task_id),
            "message": f"Task created: #{task_id} - {name}"
        }

    def complete_task(self, task_id: int) -> dict:
        """Mark task as complete by moving it to the Done/folded stage."""
        task_rows = self.call("project.task", "read", [[task_id]], {"fields": ["project_id", "name"]})
        if not task_rows:
            return {"success": False, "error": f"Task #{task_id} not found."}

        task = task_rows[0]
        project_id = task["project_id"][0] if task.get("project_id") else None

        done_stage = None
        if project_id:
            stages = self.call(
                "project.task.type", "search_read",
                [[("project_ids", "in", [project_id]), ("fold", "=", True)]],
                {"fields": ["id", "name"], "limit": 1, "order": "sequence desc"}
            )
            if stages:
                done_stage = stages[0]

        if not done_stage:
            generic = self.call(
                "project.task.type", "search_read",
                [[("name", "=ilike", "Done")]],
                {"fields": ["id", "name"], "limit": 1}
            )
            if generic:
                done_stage = generic[0]

        if done_stage:
            write_vals = {"stage_id": done_stage["id"]}
            if self.has_state:
                write_vals["state"] = "1_done"
            self.call("project.task", "write", [[task_id], write_vals])
            return {
                "success": True,
                "task_id": task_id,
                "name": task["name"],
                "stage": done_stage["name"],
                "url": self.task_link(task_id),
                "message": f"✅ Task #{task_id} marked as '{done_stage['name']}'."
            }

        return {"success": False, "error": "Could not identify a 'Done' stage in Odoo."}

    def update_task(
        self,
        task_id: int,
        stage_name: Optional[str] = None,
        priority: Optional[str] = None,
        deadline: Optional[str] = None,
        allocated_hours: Optional[Any] = None,
        assignee_name: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Update any properties of a task in Odoo (stage, priority, deadline, hours, assignee, title, description)."""
        task_rows = self.call("project.task", "read", [[task_id]], {"fields": ["id", "name", "project_id", "stage_id", "priority"]})
        if not task_rows:
            return {"success": False, "error": f"Task #{task_id} not found."}

        task = task_rows[0]
        project_id = task["project_id"][0] if task.get("project_id") else None
        vals = {}
        updates = []

        if name:
            vals["name"] = name.strip()
            updates.append(f"Title: '{vals['name']}'")

        if description:
            vals["description"] = description.strip()
            updates.append("Description updated")

        if priority is not None:
            p_val = "1" if str(priority).lower() in ("high", "1", "urgent", "star", "true") else "0"
            vals["priority"] = p_val
            updates.append(f"Priority: {'High ⭐' if p_val == '1' else 'Normal'}")

        if deadline:
            parsed_d = self.parse_date(deadline)
            vals["date_deadline"] = parsed_d
            updates.append(f"Deadline: {parsed_d}")

        if allocated_hours is not None:
            parsed_h = self.parse_hours(allocated_hours)
            vals["allocated_hours"] = parsed_h
            updates.append(f"Allocated Hours: {parsed_h}h")

        if stage_name:
            st_clean = stage_name.strip()
            stages = []
            if project_id:
                # Prefer stages configured for this task's project
                domain_proj = [("project_ids", "in", [project_id]), ("name", "ilike", st_clean)]
                stages = self.call("project.task.type", "search_read", [domain_proj], {"fields": ["id", "name"], "limit": 1})
            if not stages:
                domain_generic = [("name", "ilike", st_clean)]
                stages = self.call("project.task.type", "search_read", [domain_generic], {"fields": ["id", "name"], "limit": 1})

            if stages:
                target_stage = stages[0]
                vals["stage_id"] = target_stage["id"]
                if self.has_state:
                    if target_stage["name"].lower() in ("done", "completed", "closed"):
                        vals["state"] = "1_done"
                    elif target_stage["name"].lower() in ("cancelled", "canceled"):
                        vals["state"] = "1_canceled"
                    else:
                        vals["state"] = "01_in_progress"
                updates.append(f"Stage: '{target_stage['name']}'")
            else:
                return {"success": False, "error": f"Stage '{stage_name}' not found in Odoo."}

        if assignee_name:
            if assignee_name.lower().strip() in ("me", "my", "myself", "self", "i"):
                uid = self.uid
                uname = self.user
            else:
                users = self.find_users(assignee_name)
                if users:
                    uid = users[0]["id"]
                    uname = users[0]["name"]
                else:
                    uid = None

            if uid:
                if self.multi_assignee:
                    vals["user_ids"] = [(4, uid)]
                else:
                    vals["user_id"] = uid
                updates.append(f"Assignee: {uname}")
            else:
                return {"success": False, "error": f"User '{assignee_name}' not found in Odoo."}

        if not vals:
            return {"success": False, "error": "No valid fields provided to update."}

        try:
            self.call("project.task", "write", [[task_id], vals])
            return {
                "success": True,
                "task_id": task_id,
                "name": vals.get("name", task["name"]),
                "updates": updates,
                "message": f"✅ Updated Task #{task_id} ({task['name']}): " + ", ".join(updates)
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to update task: {str(e)}"}

    # ---------------------------------------------------------------- Timesheets
    def log_timesheet(
        self,
        task_id: int,
        hours: Any,
        description: str = "",
        date_str: str = None
    ) -> dict:
        """Log time spent on a task into account.analytic.line with robust parsing."""
        parsed_hours = round(self.parse_hours(hours), 2)
        parsed_date = self.parse_date(date_str)

        task_rows = self.call("project.task", "read", [[task_id]], {"fields": ["project_id", "name"]})
        if not task_rows:
            return {"success": False, "error": f"Task #{task_id} not found in Odoo."}

        task = task_rows[0]
        project_id = task["project_id"][0] if task.get("project_id") else False

        desc_text = description.strip() if description else f"Work on {task['name']}"

        vals = {
            "task_id": task_id,
            "project_id": project_id,
            "unit_amount": parsed_hours,
            "date": parsed_date,
            "name": desc_text,
            "user_id": self.uid,
        }

        # Include employee_id if available on Odoo instance
        emp_id = self._resolve_employee_id()
        if emp_id:
            vals["employee_id"] = emp_id

        try:
            line_id = self.call("account.analytic.line", "create", [vals])
            return {
                "success": True,
                "timesheet_id": line_id,
                "task_id": task_id,
                "task_name": task["name"],
                "hours": parsed_hours,
                "date": parsed_date,
                "description": desc_text,
                "message": f"⏳ Successfully logged {parsed_hours:.2f}h on #{task_id} ({task['name']}) for {parsed_date}."
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to log timesheet: {str(e)}"}

    def get_today_timesheets(self, target_date: str = None) -> List[dict]:
        """Fetch all timesheets logged by current user today (or for target_date)."""
        date_iso = self.parse_date(target_date)
        domain = [
            ("user_id", "=", self.uid),
            ("date", "=", date_iso)
        ]
        lines = self.call(
            "account.analytic.line", "search_read", [domain],
            {"fields": ["id", "task_id", "project_id", "unit_amount", "name", "date"], "order": "id desc"}
        )

        res = []
        for l in lines:
            res.append({
                "id": l["id"],
                "task_name": l["task_id"][1] if l.get("task_id") else "No Task",
                "task_id": l["task_id"][0] if l.get("task_id") else None,
                "project_name": l["project_id"][1] if l.get("project_id") else "No Project",
                "hours": round(l.get("unit_amount", 0.0), 2),
                "description": l.get("name", ""),
                "date": l.get("date", date_iso),
            })
        return res
