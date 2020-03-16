"""Orchestrator API client SDK."""

import json
import os
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class OrchestratorClient:
    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = base_url or os.getenv("AO_API_URL", "https://api.agent-orchestrator.io")
        self.api_key = api_key or os.getenv("AO_API_KEY", "")
        self._session = None

    def _request(self, method: str, path: str, data: Dict = None) -> Dict:
        url = f"{self.base_url}/api/v2{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = json.dumps(data).encode() if data else None
        req = Request(url, data=body, headers=headers, method=method)

        try:
            with urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except HTTPError as e:
            return {"error": e.code, "message": e.reason}

    def register_agent(self, name: str, agent_type: str, config: Dict = None) -> Dict:
        return self._request("POST", "/agents", {
            "name": name,
            "agent_type": agent_type,
            "config": config or {},
        })

    def list_agents(self, status: str = None) -> Dict:
        path = "/agents"
        if status:
            path += f"?status={status}"
        return self._request("GET", path)

    def get_agent(self, agent_id: str) -> Dict:
        return self._request("GET", f"/agents/{agent_id}")

    def delete_agent(self, agent_id: str) -> Dict:
        return self._request("DELETE", f"/agents/{agent_id}")

    def start_agent(self, agent_id: str) -> Dict:
        return self._request("POST", f"/agents/{agent_id}/start")

    def stop_agent(self, agent_id: str) -> Dict:
        return self._request("POST", f"/agents/{agent_id}/stop")

# 2019-01-22T18:13:52 update

# 2019-04-10T16:03:03 update

# 2019-06-26T09:36:49 update

# 2019-08-16T09:00:05 update

# 2019-08-26T19:43:11 update

# 2019-09-23T14:45:30 update

# 2019-10-21T11:37:53 update

# 2020-01-10T10:26:07 update

# 2020-02-12T09:30:49 update

# 2020-03-08T08:00:29 update

# 2020-03-16T19:59:51 update
