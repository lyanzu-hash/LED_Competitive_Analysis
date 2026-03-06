@echo off
chcp 65001 >nul
title LED竞品日报 · 打包为 EXE

echo.
echo ============================================
echo   LED竞品日报 · 打包为 EXE
echo ============================================
echo.

:: ── 1. 检查 Python ────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause & exit /b 1
)

:: ── 2. 自动安装 pyinstaller（如未安装）──────────────────────────────────────
echo [1/3] 检查并安装依赖...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo      正在安装 pyinstaller...
    pip install pyinstaller -q
)
pip install -r requirements.txt -q
echo      依赖已就绪

:: ── 3. 打包 ──────────────────────────────────────────────────────────────────
echo.
echo [2/3] 正在打包，首次约需 1-2 分钟...
echo.

python -m PyInstaller ^
    --name "LED竞品日报" ^
    --onefile ^
    --windowed ^
    --icon NONE ^
    --add-data ".env.example;." ^
    --hidden-import openpyxl ^
    --hidden-import bs4 ^
    --hidden-import lxml ^
    --hidden-import lxml.etree ^
    --hidden-import openai ^
    --hidden-import fake_useragent ^
    --collect-all openai ^
    app.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查上方错误信息。
    pause & exit /b 1
)

:: ── 4. 整理发布包 ────────────────────────────────────────────────────────────
echo.
echo [3/3] 整理发布文件...

set DIST_DIR=dist\LED竞品日报_发布包

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"

:: 复制 EXE
copy /Y "dist\LED竞品日报.exe" "%DIST_DIR%\" >nul

:: 复制 .env.example（用户首次填写 API Key）
copy /Y ".env.example" "%DIST_DIR%\.env.example" >nul

:: 生成使用说明
(
echo # 使用说明
echo.
echo ## 第一步：填写 API Key
echo 1. 将 .env.example 重命名为 .env
echo 2. 用记事本打开 .env
echo 3. 将 OPENAI_API_KEY= 后面改成你自己的 Key
echo    （如使用 DeepSeek，同时取消 OPENAI_BASE_URL 和 OPENAI_MODEL 那两行注释）
echo.
echo ## 第二步：运行程序
echo 双击 "LED竞品日报.exe" 即可打开管理面板：
echo - 在界面中填写 API Key，点击【保存配置】
echo - 点击【注册定时任务】，每天自动运行
echo - 点击【立即运行一次】，马上生成今日日报
echo.
echo ## 输出文件
echo 程序运行后，Excel 日报保存在 EXE 同目录的 output\ 文件夹中。
echo.
echo ## 常见问题
echo Q: 注册定时任务失败？
echo A: 右键 EXE → 以管理员身份运行，再点注册。
echo.
echo Q: 运行报错 API Key 无效？
echo A: 检查 .env 文件中的 Key 是否正确，注意不要有多余空格。
) > "%DIST_DIR%\使用说明.txt"

echo.
echo ============================================
echo   打包完成！发布包位于：
echo   %CD%\%DIST_DIR%
echo ============================================
echo.
echo 把整个 "LED竞品日报_发布包" 文件夹发给对方即可。
echo.
pause
