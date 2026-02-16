# -*- coding: utf-8 -*-
import json
import os
import urllib.request
import urllib.error
from typing import Optional, Dict, Any


class BackendClient:
    def __init__(self):
        self.base_url = (os.getenv("BACKEND_URL") or "").strip().rstrip("/")
        self.app_secret = (os.getenv("APP_BACKEND_SECRET") or "").strip()
        self.timeout = float(os.getenv("BACKEND_TIMEOUT", "6"))

    def enabled(self) -> bool:
        return bool(self.base_url)

    def _request(self, method: str, path: str, payload: Optional[Dict] = None) -> Dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("backend_disabled")
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Content-Type": "application/json"}
        if self.app_secret:
            headers["X-App-Secret"] = self.app_secret
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    def upsert_user(self, user_id: int, name: str, email_id: str) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/internal/upsert-user",
            {"user_id": int(user_id), "name": str(name or ""), "email_id": str(email_id or "").lower()},
        )

    def get_plan(self, user_id: int) -> Dict[str, Any]:
        return self._request("GET", f"/plans/me/{int(user_id)}")

    def activate_plan(self, user_id: int, plan_code: str) -> Dict[str, Any]:
        return self._request("POST", "/plans/activate", {"user_id": int(user_id), "plan_code": str(plan_code)})

    def consume_usage(self, user_id: int, feature_key: str, limit_per_day: int) -> Dict[str, Any]:
        return self._request(
            "POST",
            "/usage/consume",
            {
                "user_id": int(user_id),
                "feature_key": str(feature_key),
                "limit_per_day": int(limit_per_day),
            },
        )
