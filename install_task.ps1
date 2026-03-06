# 请【右键】本文件 → "以管理员身份运行 PowerShell" 后执行
# 或在管理员 PowerShell 中运行：
#   Set-ExecutionPolicy -Scope Process Bypass; .\install_task.ps1

$taskName = "LED竞品日报_每日生成"
$xmlPath  = Join-Path $PSScriptRoot "task_schedule.xml"

# 删除旧任务（如果存在）
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

# 从 XML 注册任务
Register-ScheduledTask -TaskName $taskName -Xml (Get-Content $xmlPath -Raw -Encoding Unicode)

if ($?) {
    Write-Host ""
    Write-Host "✅ 定时任务注册成功！" -ForegroundColor Green
    Write-Host "   任务名称 : $taskName"
    Write-Host "   执行时间 : 每天 08:00"
    Write-Host "   重试策略 : 失败最多重试 3 次，每次间隔 5 分钟"
    Write-Host "   日志位置 : $PSScriptRoot\logs\"
    Write-Host ""
    Write-Host "可在【任务计划程序】中查看或修改：" -ForegroundColor Cyan
    Write-Host "   Win+R → taskschd.msc → 任务计划程序库 → $taskName"
    Write-Host ""
} else {
    Write-Host "❌ 注册失败，请确认以管理员身份运行本脚本。" -ForegroundColor Red
}

Pause
