'=== Seeed Studio 认证服务 - 后台静默启动脚本 ===
'双击此文件会在后台启动服务，不弹出命令行窗口
'停止服务：在任务管理器里结束 python.exe 进程

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\seeed\Documents\Codex\2026-08-12\h\outputs\seeed-cert-agent"

' 尝试用 pythonw.exe（无窗口模式），没有就用 python.exe 隐藏窗口
Dim pythonExe
Dim fso
Set fso = CreateObject("Scripting.FileSystemObject")

If fso.FileExists("pythonw.exe") Then
    pythonExe = "pythonw.exe"
Else
    pythonExe = "python.exe"
End If

' 静默启动服务
WshShell.Run pythonExe & " app.py --host 0.0.0.0 --port 5000", 0, False

' 提示用户
MsgBox "认证查询服务已在后台启动！" & vbCrLf & vbCrLf & _
       "本机访问: http://localhost:5000" & vbCrLf & _
       "内网访问: 请查看启动日志文件" & vbCrLf & vbCrLf & _
       "停止服务：打开任务管理器，结束 python.exe 进程", _
       vbInformation, "Seeed Studio 认证服务"
