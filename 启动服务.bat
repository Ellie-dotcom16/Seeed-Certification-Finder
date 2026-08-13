@echo off
chcp 65001 >nul
echo ============================================
echo   Seeed Studio 认证查询服务
echo ============================================
echo.

REM 安装依赖（首次运行需要）
python -c "import flask" 2>nul
if %errorlevel% neq 0 (
    echo 正在安装依赖...
    pip install -r requirements.txt
    echo.
)

echo 请选择操作：
echo   1. 启动 Web 查询服务
echo   2. 全量抓取所有 SKU 认证数据
echo   3. 提取认证 PDF 中的认证号
echo   4. 导出 Excel 认证映射表
echo   5. 退出
echo.
set /p choice=请输入数字 (1-5): 

if "%choice%"=="1" (
    echo 正在启动 Web 服务...
    python app.py --host 0.0.0.0 --port 5000
)
if "%choice%"=="2" (
    echo 开始全量抓取...
    python scraper.py
)
if "%choice%"=="3" (
    echo 开始提取认证号...
    python export.py --extract-pdfs
)
if "%choice%"=="4" (
    echo 正在导出 Excel...
    python export.py --excel
)
if "%choice%"=="5" exit

pause
