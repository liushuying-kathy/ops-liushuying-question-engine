# 问题引擎每日跑批（供 Windows 任务计划程序调用）
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$env:PYTHONPATH = "tools\qdm_bdapp"
$day = Get-Date -Format "yyyy-MM-dd"
$env:ENGINE_RUN_DIR = "问题引擎\runs\$day"
python "问题引擎\scripts\run_batch.py"
python "问题引擎\scripts\run_v33_grader.py"
