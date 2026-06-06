@echo off
chcp 65001 >nul
title Textbook-RAG-Agent
setlocal enabledelayedexpansion

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║       📖 Textbook-RAG-Agent · 教材私人导师            ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

:: 激活 conda 环境
set CONDA_ENV=textbook-rag
call "E:\annaconda\Scripts\activate.bat" "E:\annaconda"
call conda activate %CONDA_ENV% 2>nul
if errorlevel 1 (
    echo [错误] 无法激活 conda 环境 %CONDA_ENV%
    echo   请先运行：conda create -n textbook-rag python=3.11 -y
    pause
    exit /b 1
)

:: 检查 .env 文件
if not exist ".env" (
    echo [警告] 未找到 .env 文件，正在从 .env.example 复制...
    copy .env.example .env >nul
    echo [提示] 请编辑 .env 文件，填入你的 API Key 后重新运行。
    echo.
    pause
    exit /b 1
)

:: 菜单
:menu
echo.
echo   当前 conda 环境: %CONDA_ENV%
echo   请选择操作:
echo   [1] 安装/更新依赖
echo   [2] 索引教材 (ingest)
echo   [3] 重新索引 (--force 强制重建)
echo   [4] 开始对话 (CLI)
echo   [5] 启动 Web UI (Streamlit)
echo   [6] 启动后端 API (FastAPI)
echo   [7] 启动前端 (React + Vite)
echo   [0] 退出
echo.

set /p choice="请输入选项 (0-7): "

if "%choice%"=="1" goto install
if "%choice%"=="2" goto ingest
if "%choice%"=="3" goto force_ingest
if "%choice%"=="4" goto chat
if "%choice%"=="5" goto webui
if "%choice%"=="0" goto end
if "%choice%"=="6" goto backend
if "%choice%"=="7" goto frontend
echo 无效选项，请重新输入。
goto menu

:install
echo.
echo [正在安装依赖...]
pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络和 Python 环境。
    pause
)
echo [完成] 依赖安装成功！
goto menu

:ingest
echo.
echo [开始索引教材...]
python -m src.ingest
echo.
pause
goto menu

:force_ingest
echo.
echo [强制重建索引...]
python -m src.ingest --force
echo.
pause
goto menu

:chat
echo.
python -m src.chat
goto menu

:webui
echo.
echo [启动 Streamlit Web UI...]
echo 浏览器将自动打开 http://localhost:8501
echo 按 Ctrl+C 停止服务器
echo.
streamlit run app.py
goto menu

:backend
echo.
echo [启动 FastAPI 后端...]
echo API 文档: http://localhost:8000/docs
echo 按 Ctrl+C 停止服务器
echo.
uvicorn backend.main:app --reload --port 8000
goto menu

:frontend
echo.
echo [启动 React 前端开发服务器...]
echo 浏览器将自动打开 http://localhost:5173
echo 请确保后端已在另一个终端启动 (选项 6)
echo 按 Ctrl+C 停止服务器
echo.
cd frontend
call npm install 2>nul
call npm run dev
cd ..
goto menu

:end
echo.
echo 再见！
exit /b 0
