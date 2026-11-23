from datetime import datetime, date, timezone
from typing import Dict, Any, Optional, List
from app.odoo.base_client import BaseOdooClient


class AttendanceOdooClient(BaseOdooClient):
    """Client for managing HR Attendance (Clock-In / Clock-Out) in Odoo."""

    def __init__(self, url: str, db: str, user: str, key: str):
        super().__init__(url, db, user, key)
        self.employee_id, self.employee_name = self._resolve_employee()

    def _resolve_employee(self) -> tuple[Optional[int], str]:
        """Find the hr.employee record corresponding to the logged in res.users uid."""
        # 1. Search by user_id
        emps = self.call(
            "hr.employee", "search_read",
            [[("user_id", "=", self.uid)]],
            {"fields": ["id", "name"], "limit": 1}
        )
        if emps:
            return emps[0]["id"], emps[0]["name"]

        # 2. Fallback: Search by user's email or name
        user_data = self.call("res.users", "read", [[self.uid]], {"fields": ["name", "email"]})
        if user_data:
            name = user_data[0].get("name")
            email = user_data[0].get("email")
            if email:
                emps = self.call(
                    "hr.employee", "search_read",
                    [[("work_email", "=ilike", email)]],
                    {"fields": ["id", "name"], "limit": 1}
                )
                if emps:
                    return emps[0]["id"], emps[0]["name"]
            if name:
                emps = self.call(
                    "hr.employee", "search_read",
                    [[("name", "=ilike", name)]],
                    {"fields": ["id", "name"], "limit": 1}
                )
                if emps:
                    return emps[0]["id"], emps[0]["name"]

        return None, "Unknown Employee"

    def get_status(self) -> Dict[str, Any]:
        """Check if employee is currently clocked in or out."""
        if not self.employee_id:
            return {
                "success": False,
                "error": "No linked HR Employee record found for your Odoo account."
            }

        # Find open attendance
        open_atts = self.call(
            "hr.attendance", "search_read",
            [[("employee_id", "=", self.employee_id), ("check_out", "=", False)]],
            {"fields": ["id", "check_in"], "limit": 1, "order": "check_in desc"}
        )

        today_iso = date.today().isoformat()
        # Fetch today's attendances to calculate total hours worked today
        today_atts = self.call(
            "hr.attendance", "search_read",
            [[
                ("employee_id", "=", self.employee_id),
                ("check_in", ">=", f"{today_iso} 00:00:00")
            ]],
            {"fields": ["id", "check_in", "check_out", "worked_hours"], "order": "check_in asc"}
        )

        total_hours_today = sum(att.get("worked_hours") or 0.0 for att in today_atts)

        if open_atts:
            active = open_atts[0]
            check_in_str = active["check_in"]
            
            # Calculate current session duration
            try:
                check_in_dt = datetime.fromisoformat(check_in_str.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                if check_in_dt.tzinfo is None:
                    check_in_dt = check_in_dt.replace(tzinfo=timezone.utc)
                current_duration_secs = (now_dt - check_in_dt).total_seconds()
                current_duration_hours = max(0.0, current_duration_secs / 3600.0)
            except Exception:
                current_duration_hours = 0.0

            return {
                "success": True,
                "is_clocked_in": True,
                "attendance_id": active["id"],
                "check_in": check_in_str,
                "employee_name": self.employee_name,
                "current_session_hours": round(current_duration_hours, 2),
                "total_hours_today": round(total_hours_today + current_duration_hours, 2)
            }
        else:
            # Last completed attendance
            last_att = today_atts[-1] if today_atts else None
            return {
                "success": True,
                "is_clocked_in": False,
                "employee_name": self.employee_name,
                "last_check_out": last_att.get("check_out") if last_att else None,
                "total_hours_today": round(total_hours_today, 2)
            }

    def clock_in(self) -> Dict[str, Any]:
        """Clock in the current employee."""
        status = self.get_status()
        if not status.get("success"):
            return status

        if status.get("is_clocked_in"):
            return {
                "success": False,
                "already_clocked_in": True,
                "message": f"You are already clocked in since {status['check_in']}."
            }

        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        vals = {
            "employee_id": self.employee_id,
            "check_in": now_utc,
        }

        try:
            att_id = self.call("hr.attendance", "create", [vals])
            return {
                "success": True,
                "attendance_id": att_id,
                "check_in": now_utc,
                "employee_name": self.employee_name,
                "message": f"✅ Clocked In successfully at {now_utc} UTC."
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to clock in: {str(e)}"}

    def clock_out(self) -> Dict[str, Any]:
        """Clock out the current employee."""
        status = self.get_status()
        if not status.get("success"):
            return status

        if not status.get("is_clocked_in"):
            return {
                "success": False,
                "already_clocked_out": True,
                "message": "You are not currently clocked in."
            }

        att_id = status["attendance_id"]
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        try:
            self.call("hr.attendance", "write", [[att_id], {"check_out": now_utc}])
            # Re-read to get computed worked_hours
            rec = self.call("hr.attendance", "read", [[att_id]], {"fields": ["check_in", "check_out", "worked_hours"]})
            session_hours = rec[0].get("worked_hours", 0.0) if rec else 0.0

            return {
                "success": True,
                "attendance_id": att_id,
                "check_out": now_utc,
                "employee_name": self.employee_name,
                "session_hours": round(session_hours, 2),
                "message": f"⏹️ Clocked Out successfully at {now_utc} UTC (Shift: {round(session_hours, 2)} hrs)."
            }
        except Exception as e:
            return {"success": False, "error": f"Failed to clock out: {str(e)}"}

    def get_today_summary(self) -> Dict[str, Any]:
        """Get full breakdown of today's attendance sessions."""
        status = self.get_status()
        today_iso = date.today().isoformat()
        today_atts = self.call(
            "hr.attendance", "search_read",
            [[
                ("employee_id", "=", self.employee_id),
                ("check_in", ">=", f"{today_iso} 00:00:00")
            ]],
            {"fields": ["id", "check_in", "check_out", "worked_hours"], "order": "check_in asc"}
        )

        sessions = []
        for a in today_atts:
            sessions.append({
                "id": a["id"],
                "check_in": a["check_in"],
                "check_out": a["check_out"] or "Ongoing",
                "hours": round(a.get("worked_hours") or 0.0, 2)
            })

        return {
            "success": True,
            "employee_name": self.employee_name,
            "is_clocked_in": status.get("is_clocked_in", False),
            "sessions": sessions,
            "total_hours": status.get("total_hours_today", 0.0)
        }
