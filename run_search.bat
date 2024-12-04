@echo off
chcp 65001
title DOI文献作者搜索工具
cls

echo === DOI文献作者搜索工具 启动程序 ===
echo.

:: 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误：未找到 Python，请先安装 Python 3.x
    echo 您可以从 https://www.python.org/downloads/ 下载安装
    echo.
    pause
    exit /b 1
)

:: 检查程序文件是否存在
if not exist search_doi.py (
    echo 错误：未找到 search_doi.py 文件
    echo 请确保该文件与本批处理文件在同一目录
    echo.
    pause
    exit /b 1
)

:: 检查并安装依赖
echo 正在检查依赖包...
echo.

python -c "import requests" 2>NUL
if errorlevel 1 (
    echo 正在安装 requests...
    pip install requests
)

python -c "import habanero" 2>NUL
if errorlevel 1 (
    echo 正在安装 habanero...
    pip install habanero
)

python -c "import Bio" 2>NUL
if errorlevel 1 (
    echo 正在安装 biopython...
    pip install biopython
)

echo.
echo 所有依赖已就绪
echo.
echo 正在启动程序...
echo.

:: 运行程序
python search_doi.py

:: 如果程序异常退出
if errorlevel 1 (
    echo.
    echo 程序异常退出，错误代码：%errorlevel%
    echo 请检查错误信息或联系技术支持
)

echo.
echo 按任意键退出...
pause >nul 