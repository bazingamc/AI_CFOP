"""
API与配置工具
"""

import os
import json
import urllib.request
from typing import List, Dict

from config import CONFIG_FILE


SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"


def fetch_models(api_key: str) -> List[str]:
    url = f"{SILICONFLOW_BASE_URL}/models?type=text&sub_type=chat"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    models = [m["id"] for m in data.get("data", []) if m.get("id")]
    return models


def load_config() -> Dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(config: Dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
