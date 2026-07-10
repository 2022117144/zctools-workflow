"""
智创AI Tools Backend — 从项目文件提取的业务逻辑后端
独立部署，接入你自己的生成工具

启动: python server.py
数据目录: ./data/
工作流目录: ./workflows/
端口: 8765 (可通过 ZCTOOLS_PORT 环境变量设置)
"""
import json, os, uuid, sys, requests, threading
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

# 流水线引擎
import pipeline as pl

# LLM 客户端
import llm as llm_mod

# 外部 API 集成
import handlers as hd

# 系统提示词管理
import prompts as prompts_mod

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel
import uvicorn

# 反缓存头
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}

# ============================================================
# 应用初始化
# ============================================================
app = FastAPI(title="智创工具", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册外部 API handler
pl.register_step_handler("photogpt_images", hd.photogpt_images_handler)
pl.register_step_handler("insmind_video", hd.insmind_video_handler)
pl.register_step_handler("bgm_send", hd.bgm_send_handler)

# 数据目录
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
WORKFLOWS_DIR = BASE_DIR / "workflows"
FRONTEND_DIR = BASE_DIR.parent / "frontend"
DATA_DIR.mkdir(parents=True, exist_ok=True)
WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)

# 挂载前端静态文件
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR), html=False), name="frontend")

@app.get("/")
def serve_root():
    return FileResponse(str(FRONTEND_DIR / "index.html"), headers=NO_CACHE_HEADERS)

@app.get("/css/{file}")
def serve_css(file: str):
    return FileResponse(str(FRONTEND_DIR / "css" / file), headers=NO_CACHE_HEADERS)

@app.get("/js/{file}")
def serve_js(file: str):
    return FileResponse(str(FRONTEND_DIR / "js" / file), headers=NO_CACHE_HEADERS)

@app.head("/css/{file}")
@app.head("/js/{file}")
async def head_static(file: str): pass

PROJECTS_FILE = DATA_DIR / "projects.json"
PROJECT_CONTENT_DIR = DATA_DIR / "project_content"
STYLES_FILE_INTERNAL = DATA_DIR / "builtin_styles.json"
STYLES_FILE_CUSTOM = DATA_DIR / "custom_styles.json"
PROMPT_TEMPLATES_FILE = DATA_DIR / "prompt_templates.json"

def load_json(path, default=None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except:
            return default if default is not None else {} if path.suffix == ".json" else {}
    return default() if callable(default) else (default if default is not None else ([] if "styles" in str(path).lower() else {}))

def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

# ============================================================
# 数据模型
# ============================================================
class ProjectContent(BaseModel):
    script_text: str = ""
    shots: list = []
    srt: list = []
    shot_data: dict = {}
    grid_size: int = 9


class Project(BaseModel):
    project_id: str = ""
    project_name: str = ""
    created_time: str = ""
    last_opened_time: str = ""
    video_path: str = ""
    project_path: str = ""

    original_story_desc: str = ""
    original_voiceover_text: str = ""
    original_full_script: str = ""
    rewritten_voiceover_text: str = ""
    rewritten_story_desc: str = ""
    rewritten_full_script: str = ""

    advanced_original_story_desc: str = ""
    advanced_original_voiceover_text: str = ""
    advanced_original_full_script: str = ""

    original_visual_style_anchor: str = ""
    advanced_original_visual_style_anchor: str = ""
    original_style_preset_id: str = ""
    advanced_original_style_preset_id: str = ""
    original_style_anchor_mode: str = ""
    advanced_original_style_anchor_mode: str = "preset"

    original_character_extract: str = ""
    original_character_roles: List = []
    original_character_global_style: str = ""
    original_user_character_style_anchor: str = ""
    advanced_original_character_extract: str = ""
    advanced_original_character_roles: List = []
    advanced_original_character_global_style: str = ""

    original_storyboard_shots: List = []
    original_video_shots: List = []
    advanced_original_storyboard_shots: List = []
    advanced_original_video_shots: List = []

    scenes: List = []
    keyframes: Dict = {}
    prompts: Dict = {}
    videos: Dict = {}
    pending_tasks: Dict = {}
    video_task_ids: Dict = {}

    original_tts_audio: str = ""
    original_tts_srt: str = ""
    original_tts_voice_display: str = ""
    original_tts_voice_name: str = ""

    original_cover_path: str = ""
    original_cover_titles: str = ""
    original_merged_video: str = ""

    video_aspect_ratio: str = "16:9"
    original_video_flow_type: str = "narration"
    advanced_original_video_flow_type: str = "narration"
    advanced_original_dialogue_language: str = "zh"
    original_studio_video_mode: str = "16:9"
    project_type: str = "advanced_original"


class StylePreset(BaseModel):
    id: str = ""
    name: str = ""
    video_anchor: str = ""
    character_anchor: str = ""

class PromptEnhanceRequest(BaseModel):
    prompt: str
    style_preset_id: str = ""
    mode: str = "t2v"
    image_description: str = ""

class PromptEnhanceResponse(BaseModel):
    enhanced_prompt: str
    style_anchor: str = ""
    character_anchor: str = ""

class ScriptGenerateRequest(BaseModel):
    topic: str
    style: str = ""
    tone: str = "叙事"
    duration_seconds: int = 30
    word_count: int = 200
    system_prompt_id: str = ""
    custom_prompt: str = ""

class GenerationRequest(BaseModel):
    prompt: str
    enhanced_prompt: str = ""
    task_type: str = "t2v"
    params: Dict[str, Any] = {}

class GenerationResponse(BaseModel):
    task_id: str
    status: str = "queued"
    created_at: str = ""

# ============================================================
# API: 项目
# ============================================================
@app.get("/api/projects")
def list_projects():
    return list(load_json(PROJECTS_FILE, {}).values())

@app.post("/api/projects")
def create_project(project: Project):
    projects = load_json(PROJECTS_FILE, {})
    if not project.project_id:
        project.project_id = f"proj_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    if not project.created_time:
        project.created_time = datetime.now().isoformat()
    project.last_opened_time = datetime.now().isoformat()
    projects[project.project_id] = project.model_dump()
    save_json(PROJECTS_FILE, projects)
    return project

@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    projects = load_json(PROJECTS_FILE, {})
    if project_id not in projects:
        raise HTTPException(404, "Project not found")
    return projects[project_id]

@app.put("/api/projects/{project_id}")
def update_project(project_id: str, project: Project):
    projects = load_json(PROJECTS_FILE, {})
    if project_id not in projects:
        raise HTTPException(404, "Project not found")
    data = project.model_dump()
    data["last_opened_time"] = datetime.now().isoformat()
    projects[project_id] = data
    save_json(PROJECTS_FILE, projects)
    return data

@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    projects = load_json(PROJECTS_FILE, {})
    if project_id not in projects:
        raise HTTPException(404, "Project not found")
    del projects[project_id]
    save_json(PROJECTS_FILE, projects)
    return {"status": "deleted"}


@app.get("/api/projects/{project_id}/content")
def get_project_content(project_id: str):
    """读取项目内容（文案、分镜、SRT、图片数据等）"""
    content_file = PROJECT_CONTENT_DIR / f"{project_id}.json"
    data = load_json(content_file, {})
    return data


@app.put("/api/projects/{project_id}/content")
async def save_project_content(project_id: str, request: Request):
    """保存项目内容"""
    body = await request.json()
    PROJECT_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
    content_file = PROJECT_CONTENT_DIR / f"{project_id}.json"
    save_json(content_file, body)
    return {"status": "saved"}


# ============================================================
# API: 风格预设
# ============================================================
@app.get("/api/styles")
def list_styles():
    builtin = load_json(STYLES_FILE_INTERNAL, [])
    custom = load_json(STYLES_FILE_CUSTOM, [])
    return builtin + custom

@app.post("/api/styles")
def create_style(style: StylePreset):
    styles = load_json(STYLES_FILE_CUSTOM, [])
    if not style.id:
        style.id = f"user_{uuid.uuid4().hex[:16]}"
    styles.append(style.model_dump())
    save_json(STYLES_FILE_CUSTOM, styles)
    return style

@app.delete("/api/styles/{style_id}")
def delete_style(style_id: str):
    styles = load_json(STYLES_FILE_CUSTOM, [])
    styles = [s for s in styles if s.get("id") != style_id]
    save_json(STYLES_FILE_CUSTOM, styles)
    return {"status": "deleted"}

# ============================================================
# API: 工作流管理
# ============================================================
@app.get("/api/workflows")
def list_workflows():
    result = []
    for f in sorted(WORKFLOWS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            result.append({"name": f.stem, "nodes": len(data)})
        except:
            pass
    return result

@app.get("/api/workflows/{name}")
def get_workflow(name: str):
    path = WORKFLOWS_DIR / f"{name}.json"
    if not path.exists():
        raise HTTPException(404, "Workflow not found")
    return json.loads(path.read_text(encoding="utf-8"))

# ============================================================
# API: 提示词增强
# ============================================================
@app.post("/api/prompt/enhance", response_model=PromptEnhanceResponse)
def enhance_prompt(req: PromptEnhanceRequest):
    style_anchor = ""
    character_anchor = ""

    if req.style_preset_id:
        builtin = load_json(STYLES_FILE_INTERNAL, [])
        custom = load_json(STYLES_FILE_CUSTOM, [])
        for s in builtin + custom:
            if s.get("id") == req.style_preset_id:
                style_anchor = s.get("video_anchor", "")
                character_anchor = s.get("character_anchor", "")
                break

    parts = []
    if style_anchor:
        parts.append(f"Style: {style_anchor}")
    if req.mode == "i2v" and req.image_description:
        parts.append(f"Input Image: {req.image_description}")
    parts.append(f"Action/Scene: {req.prompt}")
    if character_anchor:
        parts.append(f"Character: {character_anchor}")

    enhanced = ". ".join(parts)

    return PromptEnhanceResponse(
        enhanced_prompt=enhanced,
        style_anchor=style_anchor,
        character_anchor=character_anchor,
    )


# ============================================================
# API: 文案生成（AI）
# ============================================================

@app.post("/api/script/generate")
def generate_script(req: ScriptGenerateRequest):
    """用 LLM 根据主题生成完整文案脚本"""
    if not req.topic:
        raise HTTPException(400, "请提供主题")

    system_prompt = prompts_mod.fill_template(req.system_prompt_id, req.custom_prompt)
    if not system_prompt:
        system_prompt = "你是一个专业的短视频文案写手。根据用户提供的主题，生成一段自然流畅的旁白文案。"
    user_prompt = (
            f"主题：{req.topic}\n"
            f"风格：{req.style or '通用'}\n"
            f"语调：{req.tone}\n"
            f"目标时长：约{req.duration_seconds}秒\n\n"
            f"要求：\n"
            f"1. 写一段完整的旁白文案" + (f"，大约{req.word_count}字左右" if req.word_count > 0 else "") + "\n"
            f"2. 用中文，口语化，有画面感，朗朗上口\n"
            f"3. 把主题讲清楚，有起承转合\n"
            f"4. 直接输出文案内容，不要额外说明，不要说你写了多少字"
    )

    result = llm_mod.call_llm(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=4096,
    )

    if result:
        return {"script": result.strip(), "generated": True}
    return {"script": "", "generated": False, "error": "LLM 生成失败，请检查配置"}


@app.post("/api/script/modify")
def modify_script(req: ScriptGenerateRequest):
    """用 LLM 根据用户要求修改已有文案"""
    current_script = req.topic or ""
    if not current_script:
        raise HTTPException(400, "请先生成文案")
    if not req.custom_prompt:
        raise HTTPException(400, "请输入修改要求")

    system_prompt = "你是一个专业的短视频文案编辑。根据用户的要求修改已有文案，保留原意的同时满足修改需求。"
    user_prompt = (
        f"当前文案：\n{current_script}\n\n"
        f"修改要求：{req.custom_prompt}\n\n"
        f"要求：\n"
        f"1. 根据修改要求改写文案\n"
        f"2. 直接输出修改后的完整文案，不要加说明\n"
        f"3. 保持口语化、有画面感"
    )

    result = llm_mod.call_llm(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=4096,
    )

    if result:
        return {"script": result.strip(), "modified": True}
    return {"script": "", "modified": False, "error": "LLM 修改失败，请检查配置"}


# ============================================================
# API: 文案分析 → 分镜 + SRT
# ============================================================

@app.post("/api/script/analyze")
def analyze_script(req: ScriptGenerateRequest):
    """用 LLM 分析文案，生成分镜列表 + SRT 字幕"""
    topic = req.topic or ""
    if not topic:
        raise HTTPException(400, "请提供文案内容")

    system_prompt = "你是一个专业的视频分镜师和字幕师。根据文案生成分镜表和SRT字幕。"
    user_prompt = (
        f"文案内容：\n{topic}\n\n"
        f"请生成以下内容，以 JSON 格式输出：\n"
        f'{{\n'
        f'  "shots": [\n'
        f'    {{\n'
        f'      "index": 1,\n'
        f'      "scene": "场景描述（中文，20-40字）",\n'
        f'      "prompt": "画面提示词（英文，适合AI出图，30-60词）",\n'
        f'      "duration": 3\n'
        f'    }}\n'
        f'  ],\n'
        f'  "srt": [\n'
        f'    {{\n'
        f'      "index": 1,\n'
        f'      "start": "00:00:00,000",\n'
        f'      "end": "00:00:03,000",\n'
        f'      "text": "对应字幕文本"\n'
        f'    }}\n'
        f'  ]\n'
        f'}}\n\n'
        f"要求：\n"
        f"1. shots 数组每个元素对应一个镜头，prompt 用英文\n"
        f"2. srt 数组每个元素对应一条字幕，时间轴与 shots 对齐\n"
        f"3. 只输出 JSON，不要额外说明"
    )

    result = llm_mod.call_llm(
        messages=[{"role": "user", "content": user_prompt}],
        system_prompt=system_prompt,
        temperature=0.3,
        max_tokens=4096,
    )

    if result:
        import re
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                shots = parsed.get("shots", [])
                srt = parsed.get("srt", [])
                return {"shots": shots, "srt": srt, "generated": True}
            except:
                pass
        return {"shots": [], "srt": [], "generated": True, "raw": result}
    return {"shots": [], "srt": [], "generated": False, "error": "LLM 分析失败"}


# ============================================================
# API: 系统提示词管理
# ============================================================

class PromptCreateRequest(BaseModel):
    name: str
    content: str

@app.get("/api/prompts")
def list_prompts():
    """列出所有系统提示词（内置+自定义）"""
    return prompts_mod.get_all()

@app.post("/api/prompts")
def create_prompt(req: PromptCreateRequest):
    """创建自定义提示词"""
    if not req.name or not req.content:
        raise HTTPException(400, "名称和内容不能为空")
    return prompts_mod.create(req.name, req.content)

@app.put("/api/prompts/{prompt_id}")
def update_prompt(prompt_id: str, req: PromptCreateRequest):
    """修改任意提示词（内置或自定义）"""
    if not req.name or not req.content:
        raise HTTPException(400, "名称和内容不能为空")
    ok = prompts_mod.update(prompt_id, req.name, req.content)
    if not ok:
        raise HTTPException(404, "提示词不存在")
    return {"status": "updated"}

@app.delete("/api/prompts/{prompt_id}")
def delete_prompt(prompt_id: str):
    """删除提示词（内置或自定义）"""
    ok = prompts_mod.delete(prompt_id)
    if not ok:
        raise HTTPException(404, "提示词不存在")
    return {"status": "deleted"}


# ============================================================
# API: 生成任务（框架，接入你自己的工具）
# ============================================================
GENERATION_HANDLER = None

def register_generation_handler(handler):
    global GENERATION_HANDLER
    GENERATION_HANDLER = handler

@app.post("/api/generate", response_model=GenerationResponse)
def generate(req: GenerationRequest):
    task_id = uuid.uuid4().hex
    created_at = datetime.now().isoformat()

    if GENERATION_HANDLER:
        try:
            result = GENERATION_HANDLER(
                task_type=req.task_type,
                prompt=req.prompt,
                enhanced_prompt=req.enhanced_prompt,
                params=req.params,
            )
            return GenerationResponse(task_id=task_id, status="completed", created_at=created_at)
        except Exception as e:
            return GenerationResponse(task_id=task_id, status=f"error: {e}", created_at=created_at)

    return GenerationResponse(task_id=task_id, status="queued (no handler)", created_at=created_at)

@app.get("/api/generate/{task_id}/status")
def task_status(task_id: str):
    return {"task_id": task_id, "status": "unknown"}

# ============================================================
# API: 系统
# ============================================================
@app.get("/api/health")
def health():
    builtin = load_json(STYLES_FILE_INTERNAL, [])
    return {
        "status": "ok",
        "version": "1.0.0",
        "builtin_styles": len(builtin),
        "data_dir": str(DATA_DIR),
    }

@app.get("/api/info")
def info():
    builtin = load_json(STYLES_FILE_INTERNAL, [])
    return {
        "extracted_from": "智创AI高级版3.6",
        "components": {
            "workflows": ["default_t2v (text-to-video)", "default_i2v (image-to-video)"],
            "style_presets": [s["name"] for s in builtin],
            "pipeline": [
                "story/script input",
                "prompt enhancement (Gemma style)",
                "style anchor application",
                "character preset application",
                "TTS voice generation",
                "ComfyUI video generation",
                "output assembly",
            ],
        },
    }


# ============================================================
# API: LLM 配置（中转站设置）
# ============================================================

class LLMConfigRequest(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""

@app.get("/api/llm/config")
def get_llm_config():
    return llm_mod.get_status()

@app.post("/api/llm/config")
def set_llm_config(req: LLMConfigRequest):
    if req.base_url:
        llm_mod.save_config({"base_url": req.base_url, "model": req.model or "deepseek-v4-flash:cloud"})
    if req.api_key:
        llm_mod.save_api_key(req.api_key)
    return llm_mod.get_status()

@app.post("/api/llm/test")
def test_llm_connection(req: LLMConfigRequest = None):
    """测试 LLM 连通性。只验证 base_url 可达 + api_key 有效，不依赖模型。"""
    if req and req.base_url and req.api_key:
        base_url = req.base_url.rstrip("/")
        api_key = req.api_key
    else:
        config = llm_mod.get_config()
        base_url = config.get("base_url", "").rstrip("/")
        api_key = llm_mod.get_api_key()
    if not base_url or not api_key:
        return {"ok": False, "reply": "请填写 API 地址和 Key"}
    try:
        resp = requests.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
            proxies={"http": "", "https": ""},
        )
        # 能收到响应就算连通（即使是 403/401 也说明通了）
        if resp.status_code < 500:
            return {"ok": True, "reply": f"连通 ✅ (响应码 {resp.status_code})"}
        return {"ok": False, "reply": f"服务端错误 (响应码 {resp.status_code})"}
    except requests.ConnectionError:
        return {"ok": False, "reply": "无法连接，请检查地址和网络/代理"}
    except requests.Timeout:
        return {"ok": False, "reply": "连接超时，请检查地址和网络/代理"}
    except Exception as e:
        return {"ok": False, "reply": f"连接失败: {str(e)[:60]}"}

@app.get("/api/llm/models")
def list_llm_models(base_url: str = "", api_key: str = ""):
    """从配置的中转站获取可用模型列表。商汤返回已知模型。"""
    config = llm_mod.get_config()
    use_url = base_url or config.get("base_url", "")
    use_key = api_key or llm_mod.get_api_key()
    if not use_url or not use_key:
        return {"models": []}

    try:
        resp = requests.get(
            f"{use_url}/models",
            headers={"Authorization": f"Bearer {use_key}"},
            timeout=10,
            proxies={"http": "", "https": ""},
        )
        if resp.status_code != 200:
            return {"models": []}
        data = resp.json()
        models = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        return {"models": models}
        return {"models": models}
    except Exception as e:
        print(f"Fetch models error: {e}")
        return {"models": []}

        # ============================================================
# ============================================================
# API: 流水线 (Pipeline)
class PipelineRunRequest(BaseModel):
    project_id: str = ""
    config: Dict[str, Any] = {}

class PipelineHandlerStatus(BaseModel):
    step_name: str
    label: str
    registered: bool
    stub: bool

@app.get("/api/pipeline/steps")
def list_pipeline_steps():
    return [{
        "name": s["name"],
        "label": s["label"],
        "description": s["description"],
        "optional": s.get("optional", False),
        "stub": s.get("stub", False),
        "inputs": s.get("inputs", []),
    } for s in pl.PIPELINE_STEPS]

@app.get("/api/pipeline/handlers")
def list_pipeline_handlers():
    from pipeline import _handlers
    return [PipelineHandlerStatus(
        step_name=s["name"],
        label=s["label"],
        registered=s["name"] in _handlers,
        stub=not (s["name"] in _handlers or s["name"] in {"style_prompt", "script_audio", "storyboard_prompts", "ffmpeg_merge"}),
    ) for s in pl.PIPELINE_STEPS]

@app.post("/api/pipeline/run")
def run_pipeline(req: PipelineRunRequest):
    project_data = {}
    if req.project_id:
        projects = load_json(PROJECTS_FILE, {})
        project_data = projects.get(req.project_id, {})

    run = pl.PipelineRun(project_id=req.project_id)
    run.init_steps(req.config)
    pl.save_run(run)

    # 后台线程执行，API 立即返回
    def _run_bg():
        try:
            run.run_sync(project_data)
        except Exception as e:
            run.status = "error"
            run.error = str(e)
            pl.save_run(run)

    t = threading.Thread(target=_run_bg, daemon=True)
    t.start()

    return run.to_dict()

@app.get("/api/pipeline/runs")
def list_pipeline_runs(project_id: str = ""):
    if project_id:
        runs = pl.get_project_runs(project_id)
    else:
        runs = list(pl._runs.values())
    runs.sort(key=lambda r: r.created_at, reverse=True)
    return [r.to_dict() for r in runs[:20]]

@app.get("/api/pipeline/runs/{run_id}")
def get_pipeline_run(run_id: str):
    run = pl.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run.to_dict()

@app.post("/api/pipeline/runs/{run_id}/retry")
def retry_pipeline_run(run_id: str):
    run = pl.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "error":
        raise HTTPException(400, "Only failed runs can be retried")
    project_data = {}
    if run.project_id:
        projects = load_json(PROJECTS_FILE, {})
        project_data = projects.get(run.project_id, {})
    for step in run.steps:
        if step["status"] == "error":
            step["status"] = "pending"
            step["error"] = ""
            step["output"] = {}
    result = run.run_sync(project_data)
    pl.save_run(run)
    return result

@app.post("/api/pipeline/runs/{run_id}/cancel")
def cancel_pipeline_run(run_id: str):
    """取消正在执行的流水线"""
    run = pl.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.status != "running":
        return {"status": "already_stopped", "message": "流水线已结束"}
    run.cancel_requested = True
    pl.save_run(run)
    return {"status": "cancelling"}


# ============================================================
# API: 单帧/视频生成（前端调用）
# ============================================================

class FrameGenRequest(BaseModel):
    prompt: str
    aspect_ratio: str = "16:9"
    mode: str = "first_frame"  # first_frame / last_frame

class VideoGenRequest(BaseModel):
    prompt: str
    first_frame: str = ""
    last_frame: str = ""
    model: str = "Pixverse-V6.0"
    ratio: str = "16:9"
    resolution: str = "360p"
    duration: int = 5

import httpx as _httpx

@app.get("/api/image-proxy")
def image_proxy(url: str):
    """代理加载图片（绕过CORS/CDN限制）"""
    if not url:
        raise HTTPException(400, "url 参数不能为空")
    try:
        relay_url = f"http://localhost:8005/api/photogpt/image-proxy?url={url}"
        resp = _httpx.get(relay_url, timeout=15, follow_redirects=True)
        if resp.status_code == 200:
            ct = resp.headers.get("content-type", "image/png")
            return Response(content=resp.content, media_type=ct)
        resp = _httpx.get(url, timeout=15, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0", "Referer": "https://photogpt.io/"})
        ct = resp.headers.get("content-type", "image/png")
        return Response(content=resp.content, media_type=ct)
    except Exception as e:
        raise HTTPException(502, f"图片加载失败: {e}")

@app.post("/api/generate-frame")
def generate_frame(req: FrameGenRequest):
    """单张分镜图片生成 — 调 photogpt"""
    if not req.prompt:
        raise HTTPException(400, "prompt 不能为空")
    try:
        resp = _httpx.post(
            f"http://localhost:8005/api/photogpt/generate",
            json={
                "prompt": req.prompt,
                "aspect_ratio": req.aspect_ratio,
                "output_num": 1,
                "quality": "medium",
                "resolution": "1K",
            },
            timeout=30,
        )
        data = resp.json()
        if data.get("success"):
            job_id = data["job_id"]
            image_url = _poll_photogpt_result(job_id)
            if image_url:
                return {"success": True, "image_url": image_url, "job_id": job_id}
            return {"success": False, "error": "图片生成超时", "job_id": job_id}
        return {"success": False, "error": data.get("error", "提交失败")}
    except _httpx.ConnectError:
        raise HTTPException(502, "无法连接 PhotoGPT 后端 (localhost:8005)")
    except Exception as e:
        raise HTTPException(502, f"生成失败: {e}")

def _poll_photogpt_result(job_id: int, max_poll: int = 60) -> str:
    """轮询 photogpt 直到拿到图片 URL"""
    import time
    for i in range(max_poll):
        time.sleep(3)
        try:
            resp = _httpx.get(
                f"http://localhost:8005/api/photogpt/generate/jobs?page=1&page_size=200",
                timeout=10,
            )
            jobs = resp.json()
            for job in jobs:
                if job.get("id") == job_id:
                    if job.get("status") == "success":
                        urls = job.get("output_urls", [])
                        if urls:
                            return urls[0]
                        return ""
                    elif job.get("status") == "failed":
                        return ""
                    break
        except:
            pass
    return ""

@app.post("/api/generate-video")
def generate_video(req: VideoGenRequest):
    """单段分镜视频生成 — 调 insmind"""
    if not req.prompt:
        raise HTTPException(400, "prompt 不能为空")
    try:
        payload = {
            "job_type": "video",
            "prompt": req.prompt,
            "model": req.model,
            "ratio": req.ratio,
            "resolution": req.resolution,
            "duration": req.duration,
        }
        input_images = []
        if req.first_frame:
            input_images.append(req.first_frame)
        if req.last_frame:
            input_images.append(req.last_frame)
        if input_images:
            payload["input_images"] = input_images

        resp = _httpx.post(
            f"http://localhost:8005/api/content/generate",
            json=payload, timeout=30,
        )
        if resp.status_code != 200:
            return {"success": False, "error": f"提交失败 (HTTP {resp.status_code})"}

        data = resp.json()
        job_id = data.get("id")
        if not job_id:
            return {"success": False, "error": f"返回无 job_id: {data}"}

        video_url = _poll_video_result(job_id, max_poll=120)
        if video_url:
            return {"success": True, "video_url": video_url, "job_id": job_id}
        return {"success": False, "error": "视频生成超时", "job_id": job_id}

    except _httpx.ConnectError:
        raise HTTPException(502, "无法连接视频生成后端 (localhost:8005)")
    except Exception as e:
        raise HTTPException(502, f"视频生成失败: {e}")

def _poll_video_result(job_id: int, max_poll: int = 120) -> str:
    """轮询 content generation 直到拿到 video URL"""
    import time
    for i in range(max_poll):
        time.sleep(3)
        try:
            resp = _httpx.get(f"http://localhost:8005/api/content/jobs/{job_id}", timeout=10)
            if resp.status_code == 404:
                return ""
            job_data = resp.json()
            status = job_data.get("status", "")
            if status == "success":
                urls = job_data.get("output_urls", [])
                if urls:
                    return urls[0]
                return ""
            elif status in ("failed", "error"):
                return ""
        except:
            pass
    return ""


# ============================================================
# 入口
# ============================================================
def main():
    port = int(os.environ.get("ZCTOOLS_PORT", "8765"))
    host = os.environ.get("ZCTOOLS_HOST", "0.0.0.0")

    print("=" * 50)
    print(f"ZCTools Backend v1.0.0")
    print(f"Extracted from 智创AI高级版3.6")
    print("=" * 50)
    print(f"Listening on http://{host}:{port}")
    print(f"Data dir: {DATA_DIR}")
    print()
    print("Endpoints:")
    print(f"  GET  /api/health           Health check")
    print(f"  GET  /api/info             Extracted info")
    print(f"  GET  /api/projects         List projects")
    print(f"  POST /api/projects         Create project")
    print(f"  GET  /api/styles           List style presets")
    print(f"  POST /api/styles           Create custom style")
    print(f"  GET  /api/workflows        List ComfyUI workflows")
    print(f"  POST /api/prompt/enhance   Enhance prompt with style")
    print(f"  POST /api/script/generate  AI生成文案")
    print(f"  POST /api/generate         Submit generation task")
    print()
    print("Pipeline Endpoints:")
    print(f"  GET  /api/pipeline/steps   List pipeline steps")
    print(f"  POST /api/pipeline/run     Execute pipeline")
    print(f"  GET  /api/pipeline/runs    List pipeline runs")
    print(f"  POST /api/pipeline/runs/{id}/retry  Retry failed run")
    print(f"  POST /api/pipeline/runs/{id}/cancel Cancel running pipeline")
    print()
    print("LLM Config:")
    print(f"  GET  /api/llm/config       Get LLM config status")
    print(f"  POST /api/llm/config       Save LLM config")
    print(f"  POST /api/llm/test         Test LLM connection")
    print()
    print("To connect your own generator:")
    print("  from server import register_generation_handler")
    print("  register_generation_handler(my_handler)")
    print("=" * 50)

    uvicorn.run(app, host=host, port=port, workers=1)


if __name__ == "__main__":
    main()