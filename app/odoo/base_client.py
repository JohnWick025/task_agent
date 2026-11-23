import re
import time
import urllib.parse
import xmlrpc.client
from typing import Any, Dict, List, Optional


def clean_odoo_url(raw_url: str) -> str:
    """Normalize Odoo URL: strip labels, whitespace, trailing slashes, paths (/web), and ensure https://."""
    url = (raw_url or "").strip()
    # Strip prefixes like "URL:", "url =", "1.", quotes
    url = re.sub(r"^(url|instance)\s*[:=]\s*", "", url, flags=re.IGNORECASE).strip()
    url = re.sub(r"^\d+[\.\)]\s*", "", url).strip()
    url = url.strip("'\"")

    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        parsed = urllib.parse.urlparse(url)
        cleaned = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return cleaned
    except Exception:
        return url.rstrip("/")


class BaseOdooClient:
    _MAX_RETRIES = 3

    def __init__(self, url: str, db: str, user: str, key: str):
        self.url = clean_odoo_url(url)
        self.db = (db or "").strip()
        self.user = (user or "").strip()
        self.key = (key or "").strip()
        self.uid: Optional[int] = None

        if not all([self.url, self.db, self.user, self.key]):
            raise ValueError(f"All Odoo parameters required. Received URL='{self.url}', DB='{self.db}', User='{self.user}'")

        self._authenticate()

    def _authenticate(self):
        try:
            common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
            self.uid = common.authenticate(self.db, self.user, self.key, {})
            if not self.uid:
                raise ConnectionError(
                    f"Authentication failed. Please verify:\n"
                    f"• Database name: '{self.db}'\n"
                    f"• User/Email: '{self.user}'\n"
                    f"• API Key / Password is valid and has sufficient rights."
                )
            self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        except xmlrpc.client.Fault as f:
            raise ConnectionError(f"Odoo Fault error: {f.faultString}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Odoo at {self.url}: {str(e)}")

    def call(self, model: str, method: str, args: list, kwargs: dict = None) -> Any:
        """Execute an XML-RPC call with exponential backoff retry on transient errors."""
        kwargs = kwargs or {}
        last_exc = None
        for attempt in range(self._MAX_RETRIES):
            try:
                return self.models.execute_kw(
                    self.db, self.uid, self.key, model, method, args, kwargs
                )
            except (xmlrpc.client.Fault, ConnectionError, OSError) as exc:
                last_exc = exc
                if attempt < self._MAX_RETRIES - 1:
                    time.sleep(1.5 ** attempt)
        raise last_exc

    def test_connection(self) -> Dict[str, Any]:
        """Test connection and return user name and ID."""
        user_info = self.call("res.users", "read", [[self.uid]], {"fields": ["name", "email"]})
        if user_info:
            return {"success": True, "uid": self.uid, "user": user_info[0]}
        return {"success": False, "error": "Unable to fetch user details"}
