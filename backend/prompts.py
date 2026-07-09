"""
智创工具 — 系统提示词管理
=========================
存储和管理文案生成的系统提示词模板。
内置预设 + 用户自定义。
"""
import json, uuid
from pathlib import Path
from typing import Dict, List

DATA_DIR = Path(__file__).parent / "data"
PROMPTS_FILE = DATA_DIR / "system_prompts.json"

BUILTIN_PROMPTS = [
    {
        "id": "builtin_general",
        "name": "通用叙事",
        "content": "你是一个专业的短视频文案写手。根据用户提供的主题，生成一段自然流畅的旁白文案。",
        "builtin": True,
    },
    {
        "id": "builtin_viral",
        "name": "短视频爆款",
        "content": "你是一个爆款短视频文案专家。用抓人的开头、快节奏的叙述、强情绪共鸣的方式写文案，适合15-60秒短视频。",
        "builtin": True,
    },
    {
        "id": "builtin_science",
        "name": "科普解说",
        "content": "你是一个科普类视频文案写手。用通俗易懂的语言解释复杂概念，有逻辑递进，结尾有总结或升华。",
        "builtin": True,
    },
    {
        "id": "builtin_emotional",
        "name": "情感故事",
        "content": "你是一个情感故事类文案写手。用细腻的描写、温暖或感人的语调讲述故事，让人产生共鸣。",
        "builtin": True,
    },
    {
        "id": "builtin_product",
        "name": "产品介绍",
        "content": "你是一个产品营销文案写手。突出产品卖点、用户痛点和使用场景，语气有说服力但不浮夸。",
        "builtin": True,
    },
]


def _load() -> List[Dict]:
    if PROMPTS_FILE.exists():
        try:
            return json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
        except:
            pass
    return []


def _save(prompts: List[Dict]):
    PROMPTS_FILE.write_text(json.dumps(prompts, indent=2, ensure_ascii=False), encoding="utf-8")


def get_all() -> List[Dict]:
    """返回所有提示词，内置+自定义"""
    custom = _load()
    return BUILTIN_PROMPTS + custom


def create(name: str, content: str) -> Dict:
    """创建自定义提示词"""
    prompts = _load()
    new_id = f"custom_{uuid.uuid4().hex[:12]}"
    item = {"id": new_id, "name": name, "content": content, "builtin": False}
    prompts.append(item)
    _save(prompts)
    return item


def update(prompt_id: str, name: str, content: str) -> bool:
    """修改任意提示词（内置或自定义）"""
    # 检查内置
    for p in BUILTIN_PROMPTS:
        if p["id"] == prompt_id:
            p["name"] = name
            p["content"] = content
            return True
    # 检查自定义
    prompts = _load()
    for p in prompts:
        if p["id"] == prompt_id:
            p["name"] = name
            p["content"] = content
            _save(prompts)
            return True
    return False


def delete(prompt_id: str) -> bool:
    """删除提示词（内置或自定义）"""
    # 内置：标记为已删除（从返回列表中移除）
    # 自定义：从文件删除
    prompts = _load()
    before = len(prompts)
    prompts = [p for p in prompts if p["id"] != prompt_id]
    if len(prompts) < before:
        _save(prompts)
        return True
    # 检查是否是内置
    for p in BUILTIN_PROMPTS:
        if p["id"] == prompt_id:
            # 删除内置：从 BUILTIN_PROMPTS 移除（运行期）
            BUILTIN_PROMPTS[:] = [bp for bp in BUILTIN_PROMPTS if bp["id"] != prompt_id]
            return True
    return False


def get_by_id(prompt_id: str) -> Dict:
    """根据 ID 查找提示词"""
    for p in get_all():
        if p["id"] == prompt_id:
            return p
    return {}


def fill_template(prompt_id: str = "", custom_content: str = "") -> str:
    """获取最终的系统提示词"""
    if custom_content:
        return custom_content
    if prompt_id:
        p = get_by_id(prompt_id)
        if p:
            return p["content"]
    # 默认
    return BUILTIN_PROMPTS[0]["content"]