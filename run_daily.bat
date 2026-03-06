@echo off
:: 切换到脚本所在目录，保证相对路径正确
cd /d "%~dp0"

:: 使用 conda base 环境中的 Python（根据实际安装路径修改）
call D:\miniConda\Scripts\activate.bat base

python run_daily.py

:: 退出码透传给任务计划程序（非 0 表示失败）
exit /b %ERRORLEVEL%
