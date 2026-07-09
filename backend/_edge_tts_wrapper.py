"""独立进程调用 edge-tts，避免 Windows asyncio 冲突 + 代理干扰"""
import sys, os, json

# 强制清除所有代理环境变量（edge-tts 必须直连）
for k in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"]:
    os.environ.pop(k, None)

# 清理可能冲突的 asyncio 环境变量
os.environ.pop("PYTHONASYNCIODLL", None)

# 强制使用 selector 事件循环
import asyncio
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except:
        pass

import edge_tts

async def main():
    text = sys.argv[1]
    voice = sys.argv[2]
    output = sys.argv[3]
    
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output)
    
    size = os.path.getsize(output)
    duration_ms = int(size / 24000 * 1000)
    print(json.dumps({"success": True, "path": output, "duration_ms": duration_ms}))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}))
        sys.exit(1)