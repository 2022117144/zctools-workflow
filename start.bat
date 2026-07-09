@echo off
chcp 65001 >nul
title 智创工具

echo ========================================
echo   智创工具 v1.0
echo   从 智创AI高级版3.6 提取
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 安装依赖
echo [安装] 检查依赖...
pip install fastapi uvicorn pydantic -q

:: 启动后端
echo [启动] 服务启动中...
start "智创工具-后端" /B python backend\server.py

:: 等待
timeout /t 3 /nobreak >nul

:: 打开浏览器
echo [完成] 打开浏览器...
echo 地址: http://localhost:8765
start http://localhost:8765

echo.
echo 按任意键停止服务...
pause >nul
taskkill /f /im python.exe >nul 2>&1
echo 已停止。