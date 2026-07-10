"""
智创工具 — 流水线引擎
=====================
按手绘流程图定义的 AI 视频自动生成管线：
  风格提示词(可选) → 文案+STR音频 → 分镜提示词
    → photogpt(待接) → 分镜图片
    → insm后端(待接) → 视频
    → ffmpeg(待接) → 整合视频
    → +BGM(待接) → 发送(待接)

每步 handler 可插拔注册，未注册时返回"待接"桩。
"""

import json, os, uuid, requests, time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# LLM 客户端（相对导入）
import sys
sys.path.insert(0, str(Path(__file__).parent))
import llm as llm_mod

# ============================================================
# 步骤定义
# ============================================================

# 标准步骤列表（按顺序执行）
PIPELINE_STEPS = [
    {
        "name": "style_prompt",
        "label": "风格提示词",
        "description": "选择/注入视觉风格锚点（可选）",
        "optional": True,
        "inputs": ["style_preset_id", "style_anchor", "character_anchor"],
    },
    {
        "name": "script_audio",
        "label": "文案 + STR音频",
        "description": "输入文案脚本，生成旁白/配音音频",
        "optional": False,
        "inputs": ["script_text", "voice_name"],
    },
    {
        "name": "storyboard_prompts",
        "label": "分镜提示词",
        "description": "从文案+风格生成逐镜头画面描述",
        "optional": False,
        "inputs": ["shot_count"],
    },
    {
        "name": "photogpt_images",
        "label": "分镜图片 (photogpt)",
        "description": "调用 PhotoGPT 为每个分镜生成图片",
        "optional": False,
        "inputs": ["prompts"],
    },
    {
        "name": "insmind_video",
        "label": "视频生成 (insm后端)",
        "description": "通过 insMind 后端为每个分镜生成视频片段",
        "optional": False,
        "inputs": ["image_paths"],
    },
    {
        "name": "ffmpeg_merge",
        "label": "整合视频 (ffmpeg)",
        "description": "拼接所有视频片段为完整视频 + 可选配乐",
        "optional": False,
        "inputs": ["video_paths", "bgm_path"],
    },
    {
        "name": "bgm_send",
        "label": "加BGM → 发送",
        "description": "添加背景音乐并导出/发送成品（BGM源待接）",
        "optional": False,
        "inputs": ["merged_video_path", "bgm_path"],
    },
]

# ============================================================
# Handler 类型
# ============================================================
# handler(project_data: dict, step_config: dict) -> dict
# 返回: {"success": bool, "output": dict, "error": str}
StepHandler = Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]

# ============================================================
# Handler 注册表
# ============================================================
_handlers: Dict[str, StepHandler] = {}

# 内置"待接"桩 handler
def _stub_handler(project_data: dict, step_config: dict) -> dict:
    return {
        "success": True,
        "output": {"stub": True, "message": "接口待接 — 输出占位"},
        "error": "",
    }

# 内置"已就绪"handler（不需要外部 API 的步骤）
def _style_prompt_handler(project_data: dict, step_config: dict) -> dict:
    style_id = step_config.get("style_preset_id", "")
    style_anchor = step_config.get("style_anchor", "")
    char_anchor = step_config.get("character_anchor", "")
    return {
        "success": True,
        "output": {
            "style_preset_id": style_id,
            "style_anchor": style_anchor,
            "character_anchor": char_anchor,
        },
        "error": "",
    }

DOUBAO_TTS_API_KEY = os.environ.get("DOUBAO_SPEECH_API_KEY", "")
DOUBAO_TTS_RESOURCE_ID = "seed-tts-2.0"
DOUBAO_TTS_SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/tts/submit"
DOUBAO_TTS_QUERY_URL = "https://openspeech.bytedance.com/api/v3/tts/query"
TTS_OUTPUT_DIR = Path(__file__).parent / "data" / "tts_output"


def _call_edge_tts(text: str, voice: str = "zh-CN-XiaoxiaoNeural") -> dict:
    """
    调用 edge-tts（本地免费）生成音频。
    10秒超时机制 — 超时或失败时直接跳过（不阻塞流水线）。
    """
    TTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    task_id = uuid.uuid4().hex[:16]
    audio_path = TTS_OUTPUT_DIR / f"{task_id}.mp3"

    import subprocess as _sp
    wrapper = str(Path(__file__).parent / "_edge_tts_wrapper.py")
    env = os.environ.copy()
    for k in list(env.keys()):
        if k.upper() in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "PYTHONPATH", "PYTHONHOME", "PYTHONASYNCIODLL"):
            env.pop(k, None)

    # 只尝试 1 次，10 秒超时
    try:
        proc = _sp.run(
            [sys.executable, wrapper, text, voice, str(audio_path)],
            capture_output=True, text=True, timeout=10,
            env=env,
        )
    except (_sp.TimeoutExpired, Exception):
        return {"success": True, "output": {"skipped": True, "message": "TTS 超时（10s），已跳过"}}

    if proc.returncode == 0 and audio_path.exists():
        try:
            data = json.loads(proc.stdout)
            if data.get("success"):
                return {
                    "success": True,
                    "output": {
                        "audio_path": data["path"],
                        "duration_ms": data.get("duration_ms", 0),
                        "task_id": task_id,
                        "voice": voice,
                    }
                }
        except json.JSONDecodeError:
            pass

    # 失败 → 跳过
    return {"success": True, "output": {"skipped": True, "message": "TTS 生成失败，已跳过"}}


def _script_audio_handler(project_data: dict, step_config: dict) -> dict:
    script_text = step_config.get("script_text", "")
    if not script_text:
        script_text = project_data.get("original_full_script", "") or project_data.get("original_story_desc", "")
    voice_name = step_config.get("voice_name", "zh-CN-XiaoxiaoNeural")

    # 映射 doubao 语音名到 edge-tts 语音名
    voice_map = {
        "zh_female_vv_uranus_bigtts": "zh-CN-XiaoxiaoNeural",
        "zh_female_2024_songs_female": "zh-CN-XiaoyiNeural",
        "zh_female_2024_conversational_female": "zh-CN-XiaoxiaoNeural",
        "zh_female_2024_story_female": "zh-CN-XiaoxiaoNeural",
        "zh_male_2024_story_male": "zh-CN-YunxiNeural",
    }
    mapped_voice = voice_map.get(voice_name, voice_name)

    if not script_text:
        return {
            "success": True,
            "output": {"message": "无文案内容，跳过 STR 生成", "audio_path": "", "srt_path": ""},
            "error": "",
        }

    result = _call_edge_tts(script_text, mapped_voice)
    if result["success"]:
        output = result.get("output", {})
        # 检查是否跳过
        if output.get("skipped"):
            return {
                "success": True,
                "output": {
                    "script_text": script_text,
                    "voice_name": mapped_voice,
                    "audio_path": "",
                    "srt_path": "",
                    "duration_ms": 0,
                    "skipped": True,
                    "message": output.get("message", "TTS 已跳过"),
                },
                "error": "",
            }
        return {
            "success": True,
            "output": {
                "script_text": script_text,
                "voice_name": mapped_voice,
                "audio_path": output.get("audio_path", ""),
                "srt_path": "",
                "duration_ms": output.get("duration_ms", 0),
            },
            "error": "",
        }
    else:
        # 失败也跳过（不阻塞）
        return {
            "success": True,
            "output": {
                "script_text": script_text,
                "voice_name": mapped_voice,
                "audio_path": "",
                "srt_path": "",
                "duration_ms": 0,
                "skipped": True,
                "message": result.get("error", "TTS 失败，已跳过"),
            },
            "error": "",
        }

def _storyboard_prompts_handler(project_data: dict, step_config: dict) -> dict:
    """用 LLM 从文案+风格生成分镜提示词列表"""
    script_text = step_config.get("script_text", "")
    if not script_text:
        script_text = project_data.get("original_full_script", "") or project_data.get("original_story_desc", "")
    if not script_text:
        script_text = project_data.get("original_voiceover_text", "") or project_data.get("rewritten_voiceover_text", "")

    shot_count = step_config.get("shot_count", 5)
    style_anchor = step_config.get("style_anchor", "")
    style_preset_id = step_config.get("style_preset_id", "")

    if not script_text:
        return {"success": True, "output": {"shots": [], "shot_count": 0, "message": "无文案内容"}, "error": ""}

    # 用 LLM 生成分镜
    system_prompt = "你是一个专业的视频分镜师。根据用户提供的文案，生成结构化的分镜表。"
    user_prompt = (
        f"文案内容：\n{script_text}\n\n"
        f"请将以上文案拆分为 {shot_count} 个分镜镜头，每个镜头包含：\n"
        f"1. scene：场景描述（中文，30-50字）\n"
        f"2. prompt：画面提示词（英文，适合AI出图，50-100词）\n"
        f"3. duration：镜头时长（秒）\n"
    )
    if style_anchor:
        user_prompt += f"\n视觉风格锚点：{style_anchor}\n请将风格融入每个镜头的画面描述中。\n"

    user_prompt += (
        f"\n以 JSON 格式输出，格式为：\n"
        f'[{{"scene":"场景描述","prompt":"画面提示词","duration":3}},...]\n'
        f"只输出 JSON 数组，不要输出其他内容。"
    )

    result = llm_mod.call_llm(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=4096,
    )

    # 解析 LLM 返回
    shots = []
    if result:
        import re
        # 尝试提取 JSON 数组
        json_match = re.search(r'\[[\s\S]*\]', result)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                for i, item in enumerate(parsed):
                    shots.append({
                        "index": i,
                        "scene": item.get("scene", ""),
                        "prompt": item.get("prompt", ""),
                        "enhanced_prompt": item.get("prompt", ""),
                        "duration": item.get("duration", 3),
                    })
            except:
                pass

    # 如果 LLM 失败，fallback 到简单拆分
    if not shots:
        import re
        text = script_text
        sentences = [s.strip() for s in re.split(r'[。！？.!?\n]', text) if s.strip()]
        for i, s in enumerate(sentences[:shot_count]):
            shots.append({
                "index": i,
                "scene": s,
                "prompt": s,
                "enhanced_prompt": "",
                "duration": 3,
            })

    return {
        "success": True,
        "output": {
            "shots": shots,
            "shot_count": len(shots),
            "llm_generated": bool(result),
        },
        "error": "",
    }

def _ffmpeg_merge_handler(project_data: dict, step_config: dict) -> dict:
    """ffmpeg 视频拼接（框架，实际 ffmpeg 调用待接）"""
    video_paths = step_config.get("video_paths", [])
    bgm_path = step_config.get("bgm_path", "")
    return {
        "success": True,
        "output": {
            "video_paths": video_paths,
            "bgm_path": bgm_path,
            "merged_path": "",
            "has_bgm": bool(bgm_path),
        },
        "error": "",
    }


def register_step_handler(step_name: str, handler: StepHandler):
    """注册步骤 handler。调用后该步骤不再返回"待接"桩。"""
    _handlers[step_name] = handler


def get_step_handler(step_name: str) -> StepHandler:
    """获取步骤 handler，未注册时根据步骤定义决定用内置还是桩"""
    if step_name in _handlers:
        return _handlers[step_name]
    # 内置 handler
    builtin = {
        "style_prompt": _style_prompt_handler,
        "script_audio": _script_audio_handler,
        "storyboard_prompts": _storyboard_prompts_handler,
        "ffmpeg_merge": _ffmpeg_merge_handler,
    }
    if step_name in builtin:
        return builtin[step_name]
    # 默认桩
    return _stub_handler


# ============================================================
# 流水线状态管理
# ============================================================

class PipelineRun:
    """单次流水线执行的状态"""
    def __init__(self, project_id: str = ""):
        self.run_id = f"run_{uuid.uuid4().hex[:12]}"
        self.project_id = project_id
        self.status = "idle"  # idle | running | completed | error | cancelled
        self.steps: List[Dict[str, Any]] = []
        self.current_step: int = -1
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
        self.error = ""
        self.cancel_requested = False

    def init_steps(self, config: Dict[str, Any]):
        """用配置初始化步骤状态"""
        self.steps = []
        for step_def in PIPELINE_STEPS:
            name = step_def["name"]
            step_config = config.get(name, {})
            self.steps.append({
                "name": name,
                "label": step_def["label"],
                "description": step_def["description"],
                "optional": step_def.get("optional", False),
                "stub": step_def.get("stub", False),
                "status": "pending",
                "config": step_config,
                "output": {},
                "error": "",
            })
        self.status = "idle"
        self.current_step = -1

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "status": self.status,
            "current_step": self.current_step,
            "steps": [
                {
                    "name": s["name"],
                    "label": s["label"],
                    "description": s["description"],
                    "optional": s["optional"],
                    "stub": s.get("stub", False),
                    "status": s["status"],
                    "output_summary": _summarize_output(s.get("output", {})),
                    "error": s.get("error", ""),
                }
                for s in self.steps
            ],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }

    def run_sync(self, project_data: dict) -> dict:
        """同步执行所有步骤（每步结束后存盘，支持前端轮询）"""
        self.status = "running"
        self.updated_at = datetime.now().isoformat()
        save_run(self)

        accumulated = {}  # 累积前序步骤的输出

        for i, step in enumerate(self.steps):
            self.current_step = i

            # 检查是否请求取消
            if self.cancel_requested:
                self.status = "cancelled"
                self.error = "用户取消执行"
                save_run(self)
                return self.to_dict()

            # 可选步骤：跳过
            if step["optional"] and not step["config"]:
                step["status"] = "skipped"
                save_run(self)
                continue

            step["status"] = "running"
            self.updated_at = datetime.now().isoformat()
            save_run(self)

            # 合并累积输出到当前步骤配置
            merged_config = {**accumulated, **step["config"]}

            try:
                handler = get_step_handler(step["name"])
                result = handler(project_data, merged_config)
                if result.get("success"):
                    step["status"] = "completed"
                    step["output"] = result.get("output", {})
                    step["error"] = ""
                    # 将当前步骤输出加入累积（供后续步骤使用）
                    accumulated.update(result.get("output", {}))
                else:
                    step["status"] = "error"
                    step["error"] = result.get("error", "未知错误")
                    self.status = "error"
                    self.error = f"步骤 {step['label']} 失败: {step['error']}"
                    save_run(self)
                    return self.to_dict()
            except Exception as e:
                step["status"] = "error"
                step["error"] = str(e)
                self.status = "error"
                self.error = f"步骤 {step['label']} 异常: {e}"
                save_run(self)
                return self.to_dict()

            save_run(self)

        self.status = "completed"
        self.current_step = len(self.steps) - 1
        self.updated_at = datetime.now().isoformat()
        save_run(self)
        return self.to_dict()


def _summarize_output(output: dict) -> str:
    """输出摘要（避免塞原始数据到前端）"""
    if not output:
        return ""
    if output.get("stub"):
        return "🔌 接口待接"
    if "images" in output and "shot_count" in output:
        ok = output.get("success_count", 0)
        total = output.get("shot_count", 0)
        return f"🖼 {ok}/{total} 张图片"
    if "videos" in output and "shot_count" in output:
        ok = output.get("success_count", 0)
        total = output.get("shot_count", 0)
        return f"🎬 {ok}/{total} 个视频"
    if "shots" in output:
        return f"📋 {output.get('shot_count', 0)} 个分镜"
    if "merged_path" in output:
        return f"🎬 合成完成"
    if "style_anchor" in output and output["style_anchor"]:
        return f"🎨 {output['style_anchor'][:40]}..."
    if "script_text" in output:
        return f"📝 {len(output['script_text'])} 字"
    return "✓ 完成"


# ============================================================
# 全局 Pipeline 存储（内存 + 持久化）
# ============================================================

_runs: Dict[str, PipelineRun] = {}
RUNS_FILE = Path(__file__).parent / "data" / "pipeline_runs.json"


def save_run(run: PipelineRun):
    _runs[run.run_id] = run
    try:
        data = {k: v.to_dict() for k, v in _runs.items()}
        RUNS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except:
        pass


def load_runs():
    global _runs
    try:
        if RUNS_FILE.exists():
            data = json.loads(RUNS_FILE.read_text(encoding="utf-8"))
            for run_id, d in data.items():
                run = PipelineRun(d.get("project_id", ""))
                run.run_id = run_id
                run.status = d.get("status", "idle")
                run.current_step = d.get("current_step", -1)
                run.created_at = d.get("created_at", "")
                run.updated_at = d.get("updated_at", "")
                run.error = d.get("error", "")
                run.steps = d.get("steps", [])
                _runs[run_id] = run
    except:
        pass


def get_project_runs(project_id: str) -> List[PipelineRun]:
    return [r for r in _runs.values() if r.project_id == project_id]


def get_run(run_id: str) -> Optional[PipelineRun]:
    return _runs.get(run_id)


# 启动时加载历史
load_runs()