// ============================================================
// 智创工具 — 前端交互逻辑
// ============================================================
const API = "http://" + location.host + "/api";

// ========== 状态 ==========
let state = {
  projects: [],
  currentProject: null,
  styles: [],
  tasks: [],
  tab: "script",
  pipelineSteps: [],
  pipelineRuns: [],
  prompts: [],
  currentShots: [],
  selectedShotIdx: null,
  lastRunId: null,
};

// ========== 初始化 ==========
document.addEventListener("DOMContentLoaded", async () => {
  await loadStyles();
  await loadProjects();
  await loadPipelineSteps();
  await loadPrompts();
  checkStatus();
  // 恢复上次的文案
  const saved = localStorage.getItem("zctools_script");
  if (saved) document.getElementById("storyInput").value = saved;
  // 自动保存文案到 localStorage（也自动存到项目）
  document.getElementById("storyInput").addEventListener("input", function() {
    localStorage.setItem("zctools_script", this.value);
  });
  // 恢复上次的分镜和SRT
  const savedShots = localStorage.getItem("zctools_shots");
  const savedSrt = localStorage.getItem("zctools_srt");
  if (savedShots) renderShots(JSON.parse(savedShots));
  if (savedSrt) renderSRT(JSON.parse(savedSrt));
  if (savedShots) {
    const imgSection = document.getElementById("shotsImagesSection");
    if (imgSection) imgSection.style.display = "block";
  }
  // 恢复分镜完整数据（含图片/视频状态）
  restoreShotsFromStorage();
  // 初始化宫格
  changeGridSize();
  // 如果已有选中的项目，从后端恢复完整内容
  const sel = document.getElementById("projectSelector");
  if (sel.value) {
    await loadProjectContent(sel.value);
  }
  // 恢复上次的 Tab（刷新后保持）
  const savedTab = localStorage.getItem("zctools_active_tab");
  if (savedTab && ["script","shots","voiceover","pipeline","settings"].includes(savedTab)) {
    switchTab(savedTab);
  } else {
    switchTab("script");
  }
  // 修复浏览器自动填充问题
  const mi = document.getElementById("modifyInstruction");
  if (mi) mi.value = "";
});

// ========== API 工具 ==========
async function api(path, opts = {}) {
  const url = API + path;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...opts.headers },
    method: opts.method || (opts.body ? "POST" : "GET"),
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

// ========== 健康检查 ==========
async function checkStatus() {
  try {
    const h = await api("/health");
    document.getElementById("statusDot").className = "status-dot online";
    document.getElementById("statusText").textContent = `就绪 · ${h.builtin_styles} 风格`;
  } catch {
    document.getElementById("statusDot").className = "status-dot offline";
    document.getElementById("statusText").textContent = "后端未连接";
  }
}

// ========== 风格预设 ==========
async function loadStyles() {
  state.styles = await api("/styles");
  const sel = document.getElementById("styleSelector");
  sel.innerHTML = '<option value="">— 选择风格 —</option>';
  state.styles.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s.id;
    opt.textContent = s.name;
    sel.appendChild(opt);
  });
}

function onStyleChange() {
  const id = document.getElementById("styleSelector").value;
  const style = state.styles.find((s) => s.id === id);
  document.getElementById("styleAnchorText").textContent = style ? style.video_anchor : "（未选择）";
  document.getElementById("charAnchorText").textContent = style ? style.character_anchor : "（未选择）";
}

// ========== 项目内容持久化 ==========
async function saveProjectContent() {
  if (!state.currentProject) return;
  const script = document.getElementById("storyInput").value;
  let shots = [];
  try { shots = JSON.parse(localStorage.getItem("zctools_shots_data") || "[]"); } catch {}
  let srt = [];
  try { srt = JSON.parse(localStorage.getItem("zctools_srt") || "[]"); } catch {}
  let shotData = {};
  try { shotData = JSON.parse(localStorage.getItem("zctools_shot_data") || "{}"); } catch {}
  await api("/projects/" + state.currentProject.project_id + "/content", {
    method: "PUT",
    body: {
      script_text: script,
      shots: shots,
      srt: srt,
      shot_data: shotData,
      grid_size: parseInt(document.getElementById("gridSizeSelect")?.value) || 9,
    }
  });
}

async function loadProjectContent(projectId, clearIfEmpty = false) {
  let hasData = false;
  try {
    const content = await api("/projects/" + projectId + "/content");
    // 恢复文案
    if (content.script_text) {
      document.getElementById("storyInput").value = content.script_text;
      localStorage.setItem("zctools_script", content.script_text);
      hasData = true;
    }
    // 恢复分镜
    if (content.shots && content.shots.length > 0) {
      localStorage.setItem("zctools_shots", JSON.stringify(content.shots));
      localStorage.setItem("zctools_shots_data", JSON.stringify(content.shots));
      state.currentShots = content.shots;
      renderShots(content.shots);
      const imgSection = document.getElementById("shotsImagesSection");
      if (imgSection) imgSection.style.display = "block";
      hasData = true;
    }
    // 恢复 SRT
    if (content.srt && content.srt.length > 0) {
      localStorage.setItem("zctools_srt", JSON.stringify(content.srt));
      renderSRT(content.srt);
      hasData = true;
    }
    // 恢复分镜图片/视频数据
    if (content.shot_data && Object.keys(content.shot_data).length > 0) {
      localStorage.setItem("zctools_shot_data", JSON.stringify(content.shot_data));
      hasData = true;
    }
    // 恢复宫格尺寸
    if (content.grid_size && document.getElementById("gridSizeSelect")) {
      document.getElementById("gridSizeSelect").value = content.grid_size;
    }
    // 重新选中第一个分镜
    if (content.shots && content.shots.length > 0) {
      selectShot(0);
      changeGridSize(0);
    }
    // 如果后端没数据且 clearIfEmpty=true，清空界面（切换项目时）
    if (!hasData && clearIfEmpty) {
      clearProjectContent();
    }
  } catch (e) {
    console.warn("加载项目内容失败:", e.message);
  }
}

function clearProjectContent() {
  document.getElementById("storyInput").value = "";
  localStorage.removeItem("zctools_script");
  localStorage.removeItem("zctools_shots");
  localStorage.removeItem("zctools_shots_data");
  localStorage.removeItem("zctools_srt");
  localStorage.removeItem("zctools_shot_data");
  state.currentShots = [];
  const grid = document.getElementById("shotsGrid");
  if (grid) grid.innerHTML = '<div class="shots-placeholder">未生成分镜</div>';
  document.getElementById("shotDetailPanel").style.display = "none";
  const srtEl = document.getElementById("srtOutput");
  if (srtEl) srtEl.value = "（未生成字幕）";
}

// ========== 项目 ==========
async function loadProjects() {
  state.projects = await api("/projects");
  const sel = document.getElementById("projectSelector");
  sel.innerHTML = '<option value="">— 选择项目 —</option>';
  state.projects.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p.project_id;
    opt.textContent = p.project_name + " (" + p.project_id.slice(0, 10) + "…)";
    sel.appendChild(opt);
  });
}

async function switchProject(id) {
  // 先保存当前项目内容
  if (state.currentProject) {
    await saveProjectContent();
  }
  state.currentProject = state.projects.find((p) => p.project_id === id) || null;
  if (state.currentProject) {
    await loadProjectContent(id, true);
  } else {
    clearProjectContent();
  }
  // 切换项目后重置流水线显示
  resetPipelineDisplay();
  await loadPipelineRuns();
  // 如果该项目有正在执行的流水线，显示其当前状态
  const runningRun = state.pipelineRuns.find((r) => r.status === "running");
  if (runningRun) {
    updatePipelineRunStatus(runningRun);
    startPipelinePolling(runningRun.run_id);
  }
}

function showNewProjectModal() {
  document.getElementById("newProjectModal").classList.add("show");
  document.getElementById("newProjectName").value = "";
  setTimeout(() => document.getElementById("newProjectName").focus(), 100);
}

async function createProject() {
  const name = document.getElementById("newProjectName").value.trim();
  if (!name) return;
  await api("/projects", { body: { project_name: name } });
  closeModal("newProjectModal");
  await loadProjects();
}

async function deleteCurrentProject() {
  if (!state.currentProject) return;
  if (!confirm(`删除项目「${state.currentProject.project_name}」？`)) return;
  await api("/projects/" + state.currentProject.project_id, { method: "DELETE" });
  state.currentProject = null;
  document.getElementById("projectSelector").value = "";
  document.getElementById("storyInput").value = "";
  document.getElementById("voiceoverInput").value = "";
  await loadProjects();
}

function closeModal(id) {
  document.getElementById(id).classList.remove("show");
}

// 检查是否已选择项目
function requireProject() {
  if (!state.currentProject) {
    alert("请先选择项目");
    return false;
  }
  return true;
}

// ========== Tab 切换 ==========
function switchTab(name) {
  state.tab = name;
  localStorage.setItem("zctools_active_tab", name);
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.toggle("active", c.id === "tab-" + name));
  if (name === "pipeline") loadPipelineRuns();
  if (name === "settings") loadLLMConfig();
  if (name === "script") loadPrompts();
}

// ========== 分镜分析 + SRT ==========
async function analyzeScript() {
  if (!requireProject()) return;
  const script = document.getElementById("storyInput").value.trim();
  if (!script) { alert("请先在文案 Tab 生成或输入文案"); switchTab("script"); return; }

  const btn = document.getElementById("analyzeBtn");
  btn.disabled = true; btn.textContent = "⏳ 分析中...";

  try {
    const result = await api("/script/analyze", { body: { topic: script, style: "", tone: "叙事" } });
    if (result.generated) {
      renderShots(result.shots || []);
      renderSRT(result.srt || []);
      localStorage.setItem("zctools_shots", JSON.stringify(result.shots || []));
      localStorage.setItem("zctools_srt", JSON.stringify(result.srt || []));
      localStorage.setItem("zctools_shots_data", JSON.stringify(result.shots || []));
      state.currentShots = result.shots || [];
      const imgSection = document.getElementById("shotsImagesSection");
      if (imgSection) imgSection.style.display = "block";
    } else {
      alert("分析失败: " + (result.error || "未知错误"));
    }
  } catch (e) { alert("分析失败: " + e.message); }
  finally { btn.disabled = false; btn.textContent = "🔍 分析文案生成"; }
}

function renderShots(shots) {
  const grid = document.getElementById("shotsGrid");
  if (!grid) return;
  if (!shots || shots.length === 0) {
    grid.innerHTML = '<div class="shots-placeholder">未生成分镜</div>';
    return;
  }
  // 保存到 state 和 localStorage
  state.currentShots = shots;
  localStorage.setItem("zctools_shots_data", JSON.stringify(shots));
  grid.innerHTML = shots.map((s, i) => `
    <div class="shot-card" data-idx="${i}" onclick="selectShot(${i})">
      <div class="shot-num">${i + 1}</div>
      <div class="shot-body">
        <div class="shot-scene">${s.scene || s.prompt || ""}</div>
        <div class="shot-prompt">${s.prompt ? "🎨 " + (s.prompt.length > 40 ? s.prompt.slice(0, 40) + "..." : s.prompt) : ""}</div>
        <div class="shot-duration">⏱ ${s.duration || 3}秒</div>
      </div>
    </div>
  `).join("");
  // 默认选中第一个
  selectShot(0);
}

function renderSRT(srtList) {
  const srtEl = document.getElementById("srtOutput");
  if (!srtEl) return;
  if (!srtList || srtList.length === 0) { srtEl.value = "（未生成字幕）"; return; }
  srtEl.value = srtList.map((s, i) =>
    `${i + 1}\n${s.start || "00:00:00,000"} --> ${s.end || "00:00:03,000"}\n${s.text}\n`
  ).join("\n");
}

function changeGridSize(shotIdx) {
  const size = parseInt(document.getElementById("gridSizeSelect").value) || 9;
  const grid = document.getElementById("imageGrid");
  if (!grid) return;
  grid.setAttribute("data-size", size);
  const cols = Math.sqrt(size);
  grid.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  grid.style.gridTemplateRows = `repeat(${cols}, 1fr)`;
  grid.innerHTML = "";

  // 如果指定了分镜索引，加载该分镜的图片
  const useIdx = (shotIdx !== undefined && shotIdx !== null) ? shotIdx : state.selectedShotIdx;
  let shotImages = [];
  if (useIdx !== null && useIdx !== undefined) {
    const sd = loadShotData(useIdx);
    if (sd.firstFrame || sd.firstFrameUploaded) shotImages.push({ src: sd.firstFrame || sd.firstFrameUploaded, label: "首帧" });
    if (sd.lastFrame || sd.lastFrameUploaded) shotImages.push({ src: sd.lastFrame || sd.lastFrameUploaded, label: "尾帧" });
  }

  for (let i = 0; i < size; i++) {
    const cell = document.createElement("div");
    cell.className = "grid-cell";
    cell.dataset.idx = i;
    if (i < shotImages.length && shotImages[i].src) {
      const src = shotImages[i].src;
      if (src.startsWith("data:")) {
        cell.innerHTML = `<img src="${src}" class="grid-cell-img" alt="${shotImages[i].label}"><div class="grid-cell-label">${shotImages[i].label}</div>`;
      } else if (src.startsWith("http")) {
        cell.innerHTML = `<img src="/api/image-proxy?url=${encodeURIComponent(src)}" class="grid-cell-img" alt="${shotImages[i].label}"><div class="grid-cell-label">${shotImages[i].label}</div>`;
      } else {
        cell.innerHTML = `<div class="grid-cell-placeholder">${i + 1}</div>`;
      }
    } else {
      cell.innerHTML = `<div class="grid-cell-placeholder">${i + 1}</div>`;
    }
    grid.appendChild(cell);
  }
}

function selectShot(idx) {
  // 更新卡片选中状态
  document.querySelectorAll(".shot-card").forEach((c) => c.classList.remove("selected"));
  const card = document.querySelector(`.shot-card[data-idx="${idx}"]`);
  if (card) card.classList.add("selected");

  state.selectedShotIdx = idx;
  const shot = state.currentShots && state.currentShots[idx];
  if (!shot) return;

  // 从 localStorage 加载该分镜的图片/视频数据
  const shotData = loadShotData(idx);
  const prevShotData = idx > 0 ? loadShotData(idx - 1) : null;

  // 填充详情面板
  document.getElementById("shotDetailPanel").style.display = "block";
  document.getElementById("shotDetailTitle").textContent = `选卡 #${idx + 1}`;
  document.getElementById("shotDetailDuration").textContent = `${shot.duration || 3}秒`;
  document.getElementById("shotDetailScene").textContent = shot.scene || "";

  // === 首帧 ===
  const firstImg = document.getElementById("firstFrameImage");
  firstImg.dataset.shotIdx = idx;

  // 判断首帧来源：自己的 or 继承
    let ownFirstFrame = shotData.firstFrame || shotData.firstFrameUploaded;
    let isInherited = false;
    let inheritedUrl = "";

    if (!ownFirstFrame && idx > 0) {
      const prevData = loadShotData(idx - 1);
      const prevLast = prevData.lastFrame || prevData.lastFrameUploaded;
      if (prevLast) {
        isInherited = true;
        inheritedUrl = prevLast;
      }
    }

    const firstFrameSrc = ownFirstFrame || inheritedUrl;
    if (firstFrameSrc) {
      if (firstFrameSrc.startsWith("data:")) {
        firstImg.innerHTML = `<img src="${firstFrameSrc}" class="frame-img" alt="首帧">` + (isInherited ? '<div class="inherited-badge">⬆ 继承</div>' : '');
      } else if (firstFrameSrc.startsWith("http")) {
        firstImg.innerHTML = `<img src="/api/image-proxy?url=${encodeURIComponent(firstFrameSrc)}" class="frame-img" alt="首帧">` + (isInherited ? '<div class="inherited-badge">⬆ 继承</div>' : '');
      } else {
        firstImg.innerHTML = '<div class="frame-placeholder">未生成</div>';
      }
    } else {
      firstImg.innerHTML = '<div class="frame-placeholder">未生成</div>';
    }

  // === 尾帧 ===
  const lastImg = document.getElementById("lastFrameImage");
  lastImg.dataset.shotIdx = idx;
  const ownLastFrame = shotData.lastFrame || shotData.lastFrameUploaded;
  if (ownLastFrame && ownLastFrame.startsWith("data:")) {
    lastImg.innerHTML = `<img src="${ownLastFrame}" class="frame-img" alt="尾帧">`;
  } else if (ownLastFrame && ownLastFrame.startsWith("http")) {
    lastImg.innerHTML = `<img src="/api/image-proxy?url=${encodeURIComponent(ownLastFrame)}" class="frame-img" alt="尾帧">`;
  } else if (ownLastFrame) {
    lastImg.innerHTML = '<div class="frame-placeholder">未生成</div>';
  } else {
    lastImg.innerHTML = '<div class="frame-placeholder">未生成</div>';
  }

  // === 视频 ===
  const videoPreview = document.getElementById("shotVideoPreview");
  if (shotData.video) {
    videoPreview.innerHTML = `<video src="${shotData.video}" class="shot-video" controls></video>`;
  } else {
    videoPreview.innerHTML = '<div class="frame-placeholder">未生成</div>';
  }

  // 更新九宫格（显示当前分镜的图片）
  changeGridSize(idx);
}

// === 首帧/尾帧 上传 ===
function uploadFirstFrame() {
  document.getElementById("firstFrameUpload").click();
}
function uploadLastFrame() {
  document.getElementById("lastFrameUpload").click();
}
function handleFirstFrameUpload(e) {
  handleFrameUpload(e, "firstFrame");
}
function handleLastFrameUpload(e) {
  handleFrameUpload(e, "lastFrame");
}
function handleFrameUpload(e, type) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(ev) {
    const dataUrl = ev.target.result;
    const idx = parseInt(document.getElementById("firstFrameImage").dataset.shotIdx);
    if (type === "firstFrame") {
      saveShotData(idx, { firstFrameUploaded: dataUrl, firstFrame: "" });
    } else {
      saveShotData(idx, { lastFrameUploaded: dataUrl, lastFrame: "" });
    }
    selectShot(idx);
  };
  reader.readAsDataURL(file);
  e.target.value = "";
}

function loadShotData(idx) {
  try {
    const all = JSON.parse(localStorage.getItem("zctools_shot_data") || "{}");
    return all[idx] || {};
  } catch { return {}; }
}

function saveShotData(idx, data) {
  try {
    const all = JSON.parse(localStorage.getItem("zctools_shot_data") || "{}");
    all[idx] = { ...(all[idx] || {}), ...data };
    localStorage.setItem("zctools_shot_data", JSON.stringify(all));
  } catch {}
}

function genFirstFrame() {
  if (!requireProject()) return;
  const idx = parseInt(document.getElementById("firstFrameImage").dataset.shotIdx);
  if (isNaN(idx)) { alert("请先选择一个分镜"); return; }
  const shot = state.currentShots && state.currentShots[idx];
  if (!shot) { alert("分镜数据不存在"); return; }

  const prompt = shot.enhanced_prompt || shot.prompt || shot.scene || "";
  if (!prompt) { alert("该分镜无 prompt"); return; }

  const btn = document.getElementById("genFirstBtn");
  btn.disabled = true; btn.textContent = "⏳";

  api("/generate-frame", {
    body: { prompt: prompt, aspect_ratio: "16:9", mode: "first_frame" }
  }).then(res => {
    if (res.success && res.image_url) {
      saveShotData(idx, { firstFrame: res.image_url, firstFrameUploaded: "", firstFrameApiUrl: res.image_url });
      selectShot(idx);
      btn.disabled = false; btn.textContent = "🖼";
    } else {
      alert("首帧生成失败: " + (res.error || "未知错误"));
      btn.disabled = false; btn.textContent = "🖼";
    }
  }).catch(e => {
    alert("首帧生成失败: " + e.message);
    btn.disabled = false; btn.textContent = "🖼";
  });
}

function genLastFrame() {
  if (!requireProject()) return;
  const idx = parseInt(document.getElementById("lastFrameImage").dataset.shotIdx);
  if (isNaN(idx)) { alert("请先选择一个分镜"); return; }
  const shot = state.currentShots && state.currentShots[idx];
  if (!shot) { alert("分镜数据不存在"); return; }

  const prompt = shot.enhanced_prompt || shot.prompt || shot.scene || "";
  if (!prompt) { alert("该分镜无 prompt"); return; }

  const btn = document.getElementById("genLastBtn");
  btn.disabled = true; btn.textContent = "⏳";

  api("/generate-frame", {
    body: { prompt: prompt + ", end frame, concluding scene", aspect_ratio: "16:9", mode: "last_frame" }
  }).then(res => {
    if (res.success && res.image_url) {
      saveShotData(idx, { lastFrame: res.image_url, lastFrameUploaded: "", lastFrameApiUrl: res.image_url });
      selectShot(idx);
      btn.disabled = false; btn.textContent = "🖼";
    } else {
      alert("尾帧生成失败: " + (res.error || "未知错误"));
      btn.disabled = false; btn.textContent = "🖼";
    }
  }).catch(e => {
    alert("尾帧生成失败: " + e.message);
    btn.disabled = false; btn.textContent = "🖼";
  });
}

function genShotVideo() {
  if (!requireProject()) return;
  const idx = state.selectedShotIdx;
  if (idx === undefined || idx === null) { alert("请先选择一个分镜"); return; }
  const shot = state.currentShots && state.currentShots[idx];
  if (!shot) { alert("分镜数据不存在"); return; }

  const prompt = shot.enhanced_prompt || shot.prompt || shot.scene || "";
  if (!prompt) { alert("该分镜无 prompt"); return; }

  const shotData = loadShotData(idx);
  const prevData = idx > 0 ? loadShotData(idx - 1) : null;

  // 计算实际首尾帧
  const firstFrame = shotData.firstFrame || shotData.firstFrameUploaded ||
    (idx > 0 ? (prevData.lastFrame || prevData.lastFrameUploaded) : null);
  const lastFrame = shotData.lastFrame || shotData.lastFrameUploaded;

  const btn = document.getElementById("genVideoBtn");
  btn.disabled = true; btn.textContent = "⏳ 生成中...";

  api("/generate-video", {
    body: {
      prompt: prompt,
      first_frame: firstFrame || "",
      last_frame: lastFrame || "",
      model: "Pixverse-V6.0",
      ratio: "16:9",
      resolution: "360p",
      duration: shot.duration || 5,
    }
  }).then(res => {
    if (res.success && res.video_url) {
      saveShotData(idx, { video: res.video_url });
      selectShot(idx);
      btn.disabled = false; btn.textContent = "🎬 生成视频";
    } else {
      alert("视频生成失败: " + (res.error || "未知错误"));
      btn.disabled = false; btn.textContent = "🎬 生成视频";
    }
  }).catch(e => {
    alert("视频生成失败: " + e.message);
    btn.disabled = false; btn.textContent = "🎬 生成视频";
  });
}

// 恢复状态
function restoreShotsFromStorage() {
  try {
    const data = localStorage.getItem("zctools_shots_data");
    if (data) {
      state.currentShots = JSON.parse(data);
      renderShots(state.currentShots);
      const imgSection = document.getElementById("shotsImagesSection");
      if (imgSection && state.currentShots.length > 0) imgSection.style.display = "block";
    }
  } catch {}
}

// ========== 增强提示词 ==========
async function enhancePrompt() {
  const prompt = state.tab === "script"
    ? document.getElementById("storyInput").value
    : state.tab === "shots"
    ? getShotsText()
    : document.getElementById("voiceoverInput").value;

  if (!prompt.trim()) { alert("请先输入内容"); return; }

  const styleId = document.getElementById("styleSelector").value;
  try {
    const res = await api("/prompt/enhance", {
      body: { prompt, style_preset_id: styleId, mode: document.getElementById("modeSelect").value },
    });
    document.getElementById("enhancedPreview").textContent = res.enhanced_prompt;
  } catch (e) {
    document.getElementById("enhancedPreview").textContent = "增强失败: " + e.message;
  }
}

function getShotsText() {
  return [...document.querySelectorAll(".shot-input")]
    .map((inp, i) => `[镜头${i+1}] ${inp.value}`)
    .join("\n");
}

// ========== 生成视频 ==========
async function generateVideo() {
  if (!requireProject()) return;
  const enhanced = document.getElementById("enhancedPreview").textContent;
  if (enhanced.includes("选择一个风格预设") || !enhanced.trim()) {
    alert("请先增强提示词");
    return;
  }
  const task = { id: "task-" + Date.now(), name: "视频生成", type: "video", progress: 0, prompt: enhanced.slice(0, 40) + "…" };
  addTask(task);
  try {
    const res = await api("/generate", {
      body: {
        prompt: document.getElementById("storyInput").value || enhanced,
        enhanced_prompt: enhanced,
        task_type: document.getElementById("modeSelect").value,
        params: { aspect_ratio: document.getElementById("aspectRatio").value, duration: parseInt(document.getElementById("duration").value) },
      },
    });
    updateTask(task.id, 100, res.status === "completed" ? "完成" : res.status);
  } catch (e) {
    updateTask(task.id, 0, "失败: " + e.message);
  }
}

// ========== TTS ==========
async function genTTS() {
  if (!requireProject()) return;
  const task = { id: "tts-" + Date.now(), name: "语音生成", type: "tts", progress: 0 };
  addTask(task);
  try {
    const res = await api("/generate", {
      body: { prompt: "", enhanced_prompt: document.getElementById("voiceoverInput").value || "TTS", task_type: "tts", params: {} },
    });
    updateTask(task.id, 100, res.status === "completed" ? "完成" : res.status);
  } catch (e) {
    updateTask(task.id, 0, "失败: " + e.message);
  }
}

// ========== 任务队列 ==========
function addTask(task) { state.tasks.push(task); renderTasks(); }
function updateTask(id, progress, statusText) {
  const task = state.tasks.find((t) => t.id === id);
  if (task) { task.progress = progress; if (statusText) task.statusText = statusText; renderTasks(); }
}
function renderTasks() {
  const list = document.getElementById("taskList");
  if (state.tasks.length === 0) { list.innerHTML = '<div class="task-placeholder">暂无生成任务</div>'; return; }
  list.innerHTML = state.tasks.map((t) => `
    <div class="task-card">
      <div class="task-info"><span class="task-name">${t.name}</span><span class="task-prompt">${t.prompt || ""}</span></div>
      <div class="task-progress"><div class="progress-bar"><div class="progress-fill" style="width:${t.progress}%"></div></div><span class="progress-text">${Math.round(t.progress)}%</span></div>
    </div>`).join("");
}

// ========== 流水线 (Pipeline) ==========

async function loadPipelineSteps() {
  try {
    state.pipelineSteps = await api("/pipeline/steps");
    renderPipelineFlow();
  } catch (e) { console.warn("流水线步骤加载失败:", e.message); }
}

// 步骤 → Tab 映射
const STEP_TAB_MAP = {
  style_prompt: "script",       // 跳转到文案，聚焦右侧风格区
  script_audio: "script",
  storyboard_prompts: "shots",
  photogpt_images: "shots",
  insmind_video: "shots",
  ffmpeg_merge: "shots",
  bgm_send: "shots",
};

function renderPipelineFlow() {
  const container = document.getElementById("pipelineFlow");
  if (!container || state.pipelineSteps.length === 0) {
    if (container) container.innerHTML = '<div class="pipeline-placeholder">加载步骤定义中...</div>';
    return;
  }
  container.innerHTML = `
    <div class="pipeline-title">📋 完整流水线</div>
    <div class="pipeline-steps">
      ${state.pipelineSteps.map((s, i) => `
        <div class="pipe-step" data-step="${s.name}" onclick="goToStepTab('${s.name}')" title="点击跳转到对应功能">
          <div class="pipe-step-num">${i + 1}</div>
          <div class="pipe-step-body">
            <div class="pipe-step-name">${s.label}</div>
            <div class="pipe-step-desc">${s.description}</div>
            <div class="pipe-step-tags">
              ${s.optional ? '<span class="tag tag-optional">可选</span>' : '<span class="tag tag-required">必需</span>'}
              ${s.stub ? '<span class="tag tag-stub">待接</span>' : '<span class="tag tag-pending">等待执行</span>'}
            </div>
          </div>
        </div>
        ${i < state.pipelineSteps.length - 1 ? '<div class="pipe-arrow">↓</div>' : ''}
      `).join("")}
    </div>
  `;
}

function goToStepTab(stepName) {
  const tab = STEP_TAB_MAP[stepName] || "script";
  switchTab(tab);
  // 高亮对应的功能区域
  if (stepName === "style_prompt") {
    setTimeout(() => {
      document.getElementById("styleSelector")?.focus();
      document.getElementById("styleSelector")?.scrollIntoView({ behavior: "smooth" });
    }, 100);
  }
}

function resetPipelineDisplay() {
  // 重渲染流水线步骤（从步骤定义重建 DOM）
  renderPipelineFlow();
  // 清空执行记录列表
  const listEl = document.getElementById("pipelineRunList");
  if (listEl) listEl.innerHTML = '<div class="pipeline-placeholder">暂无执行记录</div>';
  // 重置右侧面板流水线状态
  const rightStatus = document.getElementById("rightPipelineStatus");
  if (rightStatus) {
    const labels = ["文案", "STR", "分镜", "图片", "视频", "合成", "发送"];
    rightStatus.innerHTML = labels.map((l, i) =>
      `<div>步骤 ${i + 1}/7 · ${l} ⏳</div>`
    ).join("") + '<div style="color:var(--text-muted);margin-top:8px;font-size:10px">点击流水线 Tab 查看详情</div>';
  }
  // 清除轮询
  if (pipelinePollTimer) {
    clearInterval(pipelinePollTimer);
    pipelinePollTimer = null;
  }
}

async function runPipeline() {
  if (!requireProject()) return;
  // 检查是否有文案内容
  const scriptText = document.getElementById("storyInput")?.value?.trim() || "";
  if (!scriptText) {
    alert("请先在文案 Tab 生成或输入文案内容");
    switchTab("script");
    return;
  }
  const btn = document.getElementById("runPipelineBtn");
  const stopBtn = document.getElementById("stopPipelineBtn");
  btn.disabled = true;
  btn.style.display = "none";
  stopBtn.style.display = "inline-block";
  stopBtn.textContent = "⏹ 运行中...";
  try {
    const config = {
      style_prompt: { style_preset_id: document.getElementById("styleSelector")?.value || "", style_anchor: document.getElementById("styleAnchorText")?.textContent || "", character_anchor: document.getElementById("charAnchorText")?.textContent || "" },
      script_audio: { script_text: document.getElementById("storyInput")?.value || "", voice_name: "zh-CN-XiaoxiaoNeural" },
      storyboard_prompts: { shot_count: document.querySelectorAll(".shot-card").length || 3 },
      photogpt_images: {}, insmind_video: {}, ffmpeg_merge: {}, bgm_send: {},
    };
    const projectId = state.currentProject ? state.currentProject.project_id : "";
    const result = await api("/pipeline/run", { body: { project_id: projectId, config } });
    state.lastRunId = result.run_id;
    updatePipelineRunStatus(result);
    await loadPipelineRuns();
    // 开始轮询进度
    startPipelinePolling(result.run_id);
  } catch (e) { alert("流水线执行失败: " + e.message); }
  finally { syncPipelineButtons(); }
}

let pipelinePollTimer = null;

function startPipelinePolling(runId) {
  if (pipelinePollTimer) clearInterval(pipelinePollTimer);
  pipelinePollTimer = setInterval(async () => {
    try {
      const run = await api("/pipeline/runs/" + runId);
      updatePipelineRunStatus(run);
      await loadPipelineRuns();
      if (run.status === "completed" || run.status === "error" || run.status === "cancelled") {
        clearInterval(pipelinePollTimer);
        pipelinePollTimer = null;
        syncPipelineButtons();
      }
    } catch {
      clearInterval(pipelinePollTimer);
      pipelinePollTimer = null;
    }
  }, 2000);
}

async function stopPipeline() {
  const stopBtn = document.getElementById("stopPipelineBtn");
  stopBtn.disabled = true;
  stopBtn.textContent = "⏹ 查找中...";
  
  // 实时查询最新运行记录，找到正在执行的流水线
  let runId = null;
  try {
    const runs = await api("/pipeline/runs");
    const running = runs.find((r) => r.status === "running");
    if (running) runId = running.run_id;
  } catch {}
  
  if (!runId) {
    runId = state.lastRunId; // 兜底
  }
  if (!runId) { alert("没有正在执行的流水线"); stopBtn.disabled = false; stopBtn.textContent = "⏹ 停止"; return; }
  
  stopBtn.textContent = "⏹ 停止中...";
  try {
    await api("/pipeline/runs/" + runId + "/cancel", { method: "POST" });
  } catch (e) { alert("停止失败: " + e.message); }
  finally {
    stopBtn.disabled = false;
    stopBtn.textContent = "⏹ 停止中";
  }
}

function updatePipelineRunStatus(run) {
  const container = document.getElementById("pipelineFlow");
  if (!container) return;
  const steps = run.steps || [];
  steps.forEach((step) => {
    const el = container.querySelector(`[data-step="${step.name}"]`);
    if (!el) return;
    el.className = `pipe-step pipe-${step.status}`;
    const nameEl = el.querySelector(".pipe-step-name");
    if (nameEl) { const icons = { pending: "⏳", running: "🔄", completed: "✅", error: "❌", skipped: "⏭️" }; nameEl.innerHTML = `${icons[step.status] || "⏳"} ${step.label}`; }
    const descEl = el.querySelector(".pipe-step-desc");
    if (descEl) {
      if (step.status === "completed" && step.output_summary) descEl.textContent = step.output_summary;
      else if (step.status === "error") descEl.textContent = "❌ " + (step.error || "失败");
      else if (step.status === "skipped") descEl.textContent = "已跳过（可选）";
      else descEl.textContent = step.description;
    }
  });
  const titleEl = container.querySelector(".pipeline-title");
  if (titleEl) { const icons = { idle: "📋", running: "🔄", completed: "✅ 完成", error: "❌ 失败" }; titleEl.textContent = `${icons[run.status] || "📋"} 完整流水线`; }
}

function syncPipelineButtons() {
  // 检查是否有正在执行的流水线，同步按钮状态
  const hasRunning = state.pipelineRuns.some((r) => r.status === "running");
  const btn = document.getElementById("runPipelineBtn");
  const stopBtn = document.getElementById("stopPipelineBtn");
  if (!btn || !stopBtn) return;
  if (hasRunning) {
    btn.style.display = "none";
    stopBtn.style.display = "inline-block";
    stopBtn.disabled = false;
    stopBtn.textContent = "⏹ 停止";
  } else {
    btn.style.display = "inline-block";
    btn.disabled = false;
    btn.textContent = "▶ 执行流水线";
    stopBtn.style.display = "none";
  }
}

async function loadPipelineRuns() {
  try {
    const projectId = state.currentProject ? state.currentProject.project_id : "";
    const runs = await api("/pipeline/runs" + (projectId ? "?project_id=" + projectId : ""));
    state.pipelineRuns = runs;
    
    // 同步按钮状态
    syncPipelineButtons();
    
    const listEl = document.getElementById("pipelineRunList");
    if (!listEl) return;
    if (runs.length === 0) { listEl.innerHTML = '<div class="pipeline-placeholder">暂无执行记录</div>'; return; }
    listEl.innerHTML = runs.map((r) => `
      <div class="run-card ${r.status}" onclick="showPipelineRunDetail('${r.run_id}')">
        <div class="run-card-header"><span class="run-status run-${r.status}">${statusIcon(r.status)} ${r.status}</span><span class="run-id">${r.run_id.slice(0, 12)}…</span><span class="run-time">${formatTime(r.created_at)}</span></div>
        <div class="run-card-steps">${(r.steps || []).map((s) => `<span class="step-dot step-${s.status}" title="${s.label}: ${s.status}"></span>`).join("")}</div>
      </div>`).join("");
  } catch (e) { console.warn("流水线记录加载失败:", e.message); }
}

async function showPipelineRunDetail(runId) {
  try { const run = await api("/pipeline/runs/" + runId); updatePipelineRunStatus(run); switchTab("pipeline"); }
  catch (e) { alert("加载详情失败: " + e.message); }
}

function statusIcon(status) { return { idle: "⏸", running: "🔄", completed: "✅", error: "❌" }[status] || "⏳"; }
function formatTime(iso) { if (!iso) return ""; const d = new Date(iso); return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }

// ========== AI 生成文案 ==========
async function generateScript() {
  if (!requireProject()) return;
  const topic = document.getElementById("scriptTopic").value.trim();
  if (!topic) { alert("请先输入视频主题"); return; }
  const btn = document.getElementById("genScriptBtn");
  const tone = document.getElementById("scriptTone").value;
  const wordCountRaw = document.getElementById("scriptWordCount").value.trim();
  const wordCount = wordCountRaw ? parseInt(wordCountRaw) || 0 : 0;
  const promptId = document.getElementById("promptSelector").value;
  btn.disabled = true; btn.textContent = "⏳ 生成中...";
  try {
    const result = await api("/script/generate", { body: { topic, style: "", tone, duration_seconds: 30, word_count: wordCount, system_prompt_id: promptId } });
    if (result.generated && result.script) {
      document.getElementById("storyInput").value = result.script;
      localStorage.setItem("zctools_script", result.script);
    }
    else alert("生成失败: " + (result.error || "未知错误"));
  } catch (e) { alert("生成失败: " + e.message); }
  finally { btn.disabled = false; btn.textContent = "✨ AI 生成"; }
}

// ========== AI 修改文案 ==========
async function modifyScript() {
  const instruction = document.getElementById("modifyInstruction").value.trim();
  const currentScript = document.getElementById("storyInput").value.trim();
  if (!currentScript) { alert("请先生成文案"); return; }
  if (!instruction) { alert("请输入修改要求"); return; }
  const btn = document.getElementById("modifyBtn");
  btn.disabled = true; btn.textContent = "⏳ 修改中...";
  try {
    const result = await api("/script/modify", { body: { topic: currentScript, custom_prompt: instruction } });
    if (result.modified && result.script) {
      document.getElementById("storyInput").value = result.script;
      localStorage.setItem("zctools_script", result.script);
    }
    else alert("修改失败: " + (result.error || "未知错误"));
  } catch (e) { alert("修改失败: " + e.message); }
  finally { btn.disabled = false; btn.textContent = "✨ AI 修改"; }
}

// ========== 系统提示词 ==========
async function loadPrompts() {
  try {
    state.prompts = await api("/prompts");
    const sel = document.getElementById("promptSelector");
    if (!sel) return;
    const currentVal = sel.value;
    sel.innerHTML = state.prompts.map((p) =>
      `<option value="${p.id}">${p.builtin ? "★ " : "✎ "}${p.name}</option>`
    ).join("");
    // 保持当前选中，或默认第一个
    if (currentVal && state.prompts.some(p => p.id === currentVal)) {
      sel.value = currentVal;
    }
    onPromptChange();
  } catch (e) { console.warn("提示词加载失败:", e.message); }
}

function onPromptChange() {
  const id = document.getElementById("promptSelector").value;
  const prompt = state.prompts.find((p) => p.id === id);
  const preview = document.getElementById("promptPreview");
  if (preview) preview.textContent = prompt ? prompt.content.slice(0, 120) + (prompt.content.length > 120 ? "..." : "") : "选择一种风格，AI 将按此风格生成文案";
}

function showPromptModal() {
  document.getElementById("promptModal").classList.add("show");
  renderPromptList();
  document.getElementById("newPromptName").value = "";
  document.getElementById("newPromptContent").value = "";
}

function renderPromptList() {
  const list = document.getElementById("promptList");
  if (!list) return;
  list.innerHTML = state.prompts.map((p) => `
    <div class="prompt-list-item">
      <div class="prompt-list-info">
        <strong>${p.builtin ? "★" : "✎"} ${p.name}</strong>
        <span class="prompt-list-preview">${p.content.slice(0, 80)}${p.content.length > 80 ? "..." : ""}</span>
      </div>
      <button class="btn btn-sm btn-outline" onclick="editPrompt('${p.id}')" title="编辑">✎</button>
      <button class="btn btn-sm btn-outline" onclick="deleteCustomPrompt('${p.id}')" style="color:var(--red)" title="删除">🗑</button>
    </div>`).join("");
}

function editPrompt(id) {
  const p = state.prompts.find(x => x.id === id);
  if (!p) return;
  document.getElementById("editPromptId").value = id;
  document.getElementById("newPromptName").value = p.name;
  document.getElementById("newPromptContent").value = p.content;
}

function clearPromptEditor() {
  document.getElementById("editPromptId").value = "";
  document.getElementById("newPromptName").value = "";
  document.getElementById("newPromptContent").value = "";
}

async function saveCustomPrompt() {
  const name = document.getElementById("newPromptName").value.trim();
  const content = document.getElementById("newPromptContent").value.trim();
  const editId = document.getElementById("editPromptId").value;
  if (!name || !content) { alert("请填写名称和内容"); return; }
  try {
    if (editId) {
      await api("/prompts/" + editId, { method: "PUT", body: { name, content } });
    } else {
      await api("/prompts", { body: { name, content } });
    }
    await loadPrompts();
    renderPromptList();
    clearPromptEditor();
    alert("已保存");
  } catch (e) { alert("保存失败: " + e.message); }
}

async function deleteCustomPrompt(id) {
  if (!confirm("删除此提示词？")) return;
  try {
    await api("/prompts/" + id, { method: "DELETE" });
    await loadPrompts();
    renderPromptList();
  } catch (e) { alert("删除失败: " + e.message); }
}

// ========== LLM 设置 ==========
async function loadLLMConfig() {
  try {
    const config = await api("/llm/config");
    document.getElementById("llmBaseUrl").value = config.base_url || "";
    document.getElementById("llmModel").value = config.model || "";
    document.getElementById("llmKeyStatus").textContent = config.has_key ? "🔑 已配置" : "❌ 未配置";
    document.getElementById("llmConfigInfo").innerHTML = config.has_key ? `状态：已配置 ✅ | Key: ${config.key_preview}` : "状态：未配置 ❌ 请先填写 API 地址和 Key，然后测试连接";
  } catch (e) { document.getElementById("llmConfigInfo").textContent = "加载失败: " + e.message; }
}

async function fetchModels() {
  const input = document.getElementById("llmModel");
  const dl = document.getElementById("modelList");
  const btn = document.getElementById("fetchModelsBtn");
  const baseUrl = document.getElementById("llmBaseUrl").value.trim();
  const apiKey = document.getElementById("llmApiKey").value.trim();
  if (!baseUrl || !apiKey) { alert("请先填写 API 地址和 Key 并测试连接"); return; }
  btn.disabled = true; btn.textContent = "⏳";
  input.value = "";  // 清空输入框，让 datalist 显示全部选项
  try {
    const url = "/llm/models?base_url=" + encodeURIComponent(baseUrl) + "&api_key=" + encodeURIComponent(apiKey);
    const result = await api(url);
    dl.innerHTML = "";
    if (result.models && result.models.length > 0) {
      result.models.forEach(m => {
        const opt = document.createElement("option");
        opt.value = m;
        dl.appendChild(opt);
      });
    }
    btn.textContent = "🔄 刷新";
  } catch (e) {
    btn.textContent = "🔄 刷新";
  }
  btn.disabled = false;
}

async function saveLLMConfig() {
  const baseUrl = document.getElementById("llmBaseUrl").value.trim();
  const model = document.getElementById("llmModel").value.trim();
  const apiKey = document.getElementById("llmApiKey").value.trim();
  if (!baseUrl) { alert("请先填写 API 地址"); return; }
  if (!model) { alert("请先选择模型"); return; }
  if (!apiKey) { alert("请先填写 API Key"); return; }
  try {
    const result = await api("/llm/config", { body: { base_url: baseUrl, model: model, api_key: apiKey } });
    document.getElementById("llmKeyStatus").textContent = result.has_key ? "🔑 已配置" : "❌ 未配置";
    document.getElementById("llmConfigInfo").innerHTML = result.has_key ? `状态：已配置 ✅ | Key: ${result.key_preview}` : "状态：未配置 ❌";
    document.getElementById("llmApiKey").value = "";
    if (result.configured) alert("✅ 配置已保存！现在可以生成文案了。");
  } catch (e) { alert("保存失败: " + e.message); }
}

async function testLLMConfig() {
  const baseUrl = document.getElementById("llmBaseUrl").value.trim();
  const apiKey = document.getElementById("llmApiKey").value.trim();
  if (!baseUrl) { alert("请先填写 API 地址"); return; }
  if (!apiKey) { alert("请先填写 API Key"); return; }
  const btn = document.querySelector(".settings-actions .btn-outline");
  const resultEl = document.getElementById("llmTestResult");
  btn.disabled = true; btn.textContent = "⏳ 测试中..."; resultEl.textContent = "";
  try {
    const result = await api("/llm/test", { method: "POST", body: { base_url: baseUrl, api_key: apiKey } });
    resultEl.innerHTML = result.ok ? `✅ 连接成功: "${result.reply}"` : "❌ 连接失败，请检查配置";
    resultEl.className = result.ok ? "settings-test-result success" : "settings-test-result error";
    // 测试成功后自动拉取模型列表
    if (result.ok) {
      fetchModels();
    }
  } catch (e) { resultEl.textContent = "❌ 测试失败: " + e.message; resultEl.className = "settings-test-result error"; }
  finally { btn.disabled = false; btn.textContent = "📡 测试连接"; }
}

// ========== 弹窗关闭 ==========
document.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal-overlay")) e.target.classList.remove("show");
});