"""
智创工具 — LLM 客户端
====================
通过中转站（NewAPI）调用 LLM。
不内置任何默认中转站地址，必须通过前端设置页配置。
"""
import json, os
from pathlib import Path
from typing import Dict, List, Optional

import requests

CONFIG_DIR = Path(__file__).parent / "data"
CREDENTIALS_DIR = CONFIG_DIR / "credentials"
CONFIG_FILE = CONFIG_DIR / "llm_config.json"
CREDENTIALS_FILE = CREDENTIALS_DIR / "llm_key.txt"


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)


def get_config() -> dict:
    """读取 LLM 配置。无默认值——未配置则返回空字典。"""
    ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return {}


def save_config(config: dict):
    """保存 LLM 配置（不含 API key）"""
    ensure_dirs()
    safe = {k: v for k, v in config.items() if k != "api_key"}
    CONFIG_FILE.write_text(json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8")


def get_api_key() -> str:
    """读取 API key（从独立文件，不和代码放在一起）"""
    ensure_dirs()
    if CREDENTIALS_FILE.exists():
        return CREDENTIALS_FILE.read_text(encoding="utf-8").strip()
    return ""


def save_api_key(key: str):
    """保存 API key 到独立文件"""
    ensure_dirs()
    CREDENTIALS_FILE.write_text(key.strip(), encoding="utf-8")


def is_configured() -> bool:
    """检查 LLM 是否完全配置（有 base_url + api_key + model）"""
    config = get_config()
    key = get_api_key()
    return bool(config.get("base_url")) and bool(config.get("model")) and bool(key)


def call_llm(
    messages: List[Dict[str, str]],
    system_prompt: str = "",
    model: str = "",
    temperature: float = 0,
    max_tokens: int = 2048,
) -> Optional[str]:
    """
    调用中转站 LLM，返回回复文本。
    失败返回 None。
    """
    if not is_configured():
        print("LLM call skipped: 未配置 LLM（请先在设置页配置中转站）")
        return None

    config = get_config()
    api_key = get_api_key()

    base_url = config.get("base_url", "").rstrip("/")
    model = model or config.get("model", "")
    temp = temperature if temperature > 0 else config.get("temperature", 0.7)
    mt = min(max_tokens, config.get("max_tokens", 4096))

    if not base_url or not model:
        print("LLM call skipped: base_url 或 model 为空")
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    full_messages = []
    if system_prompt:
        full_messages.append({"role": "system", "content": system_prompt})
    full_messages.extend(messages)

    body = {
        "model": model,
        "messages": full_messages,
        "temperature": temp,
        "max_tokens": mt,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            json=body,
            headers=headers,
            timeout=60,
        )
        if resp.status_code != 200:
            print(f"LLM API error: {resp.status_code} {resp.text[:200]}")
            return None
        data = resp.json()
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        return content
    except Exception as e:
        print(f"LLM call exception: {e}")
        return None


# ============================================================
# 配置 API（给前端调用）
# ============================================================

def get_status() -> dict:
    """返回当前 LLM 配置状态（不含 API key 原文）"""
    config = get_config()
    key = get_api_key()
    base_url = config.get("base_url", "")
    model = config.get("model", "")
    has_key = bool(key)
    return {
        "configured": bool(base_url) and bool(model) and has_key,
        "base_url": base_url,
        "model": model,
        "has_key": has_key,
        "key_preview": key[:12] + "..." if len(key) > 16 else "***" if key else "",
    }