@echo off
cd /d "%~dp0backend"
echo ==================================================
echo   智创工作流 — 后端服务
echo   端口: 8765
echo   关闭此窗口即停止服务
echo ==================================================
rmdir /s /q __pycache__ 2>nul
python server.py
pause