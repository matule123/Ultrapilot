$ErrorActionPreference='Stop'
$taskRoot='C:\Users\PC\Documents\GitHub\ets2la'
$taskAudit=Join-Path $taskRoot 'docs\steering-audit\oct22-sdk161'
$taskSource=Join-Path $taskAudit 'read-only-probe\UltraPilot161ReadOnlyProbe.dll'
$taskPlugins='C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\plugins'
$taskTarget=Join-Path $taskPlugins 'UltraPilot161ReadOnlyProbe.dll'
if(Get-Process -Name eurotrucks2,UltraPilot -ErrorAction SilentlyContinue){throw 'Close ETS2 and UltraPilot first'}
if(Test-Path -LiteralPath $taskTarget){throw 'Probe already exists; refusing overwrite'}
$taskReceipt=Get-Content -LiteralPath (Join-Path $taskAudit 'read-only-probe\receipt.json') -Raw | ConvertFrom-Json
if((Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReceipt.dll_sha256){throw 'Probe hash mismatch'}
$taskPreserved=@{}
foreach($taskName in @('ets2la_plugin.dll','scs-telemetry.dll','scs_sdk_controller.dll')) {
 $taskPath=Join-Path $taskPlugins $taskName
 $taskPreserved[$taskPath]=(Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash
}
$taskSettings='C:\Users\PC\AppData\Local\Programs\UltraPilot\settings.json'
$taskPreserved[$taskSettings]=(Get-FileHash -LiteralPath $taskSettings -Algorithm SHA256).Hash
Copy-Item -LiteralPath $taskSource -Destination $taskTarget
if((Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskReceipt.dll_sha256){throw 'Installed probe hash mismatch'}
foreach($taskPath in $taskPreserved.Keys){if((Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash -ne $taskPreserved[$taskPath]){throw 'Unexpected original file change'}}
$taskOutput=[ordered]@{installed_probe=$taskTarget;probe_sha256=$taskReceipt.dll_sha256;read_only=$true;production_ready=$false;originals_unchanged=$taskPreserved;remove_only_this_file=$taskTarget}
$taskOutput | ConvertTo-Json -Depth 5 | Out-File -LiteralPath (Join-Path $taskAudit 'probe-install-receipt.json') -Encoding utf8
Write-Output ('INSTALLED PASSIVE PROBE ONLY: '+$taskTarget)
Write-Output 'Original SDK DLLs and UltraPilot settings unchanged. No game/app/control started.'
