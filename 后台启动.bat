@echo off
chcp 65001 >nul
echo ============================================
echo   后台启动认证查询服务
echo ============================================
echo.

REM 安装依赖（首次）
python -c "import flask" 2>nul
if %errorlevel% neq 0 (
    echo 正在安装依赖...
    pip install -r requirements.txt
)

REM 记录当前 IP
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr IPv4') do set ip=%%a
set ip=%ip: =%

echo ============================================
echo   服务已在后台启动
echo   本机访问:   http://localhost:5000
echo   内网访问:   http://%ip%:5000
echo ============================================
echo.
echo   停止服务: 在任务管理器中结束 python.exe
echo.

REM 用 pythonw 后台运行
start "" pythonw.exe app.py --host 0.0.0.0 --port 5000

echo 按任意键关闭此窗口（服务继续在后台运行）
pause >nul
