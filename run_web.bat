@echo off
chcp 65001 >nul
title 《庆余年》卷帙秘档 · GraphRAG 智能考据阁 Web 服务
echo ========================================================
echo   《庆余年》卷帙秘档 · GraphRAG 智能考据阁 Web 服务启动
echo ========================================================
echo.
echo [1/3] 检查虚拟环境...
set PYTHON_EXE=D:\Agent\.venv\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    echo [提示] 未检测到 D:\Agent\.venv，尝试使用系统 python...
    set PYTHON_EXE=python
)

echo [2/3] 正在启动 FastAPI 后端服务 (端口: 8000)...
echo.
echo 访问网址: http://127.0.0.1:8000
echo.
start http://127.0.0.1:8000

"%PYTHON_EXE%" web_server.py
pause
