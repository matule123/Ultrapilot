# Install only the isolated sentinel-fixed diagnostic candidate. Never overwrite.
$ErrorActionPreference='Stop'
$fixedAudit='C:\Users\PC\Documents\GitHub\ets2la\docs\steering-audit\oct22-sdk161'
$fixedBuild=Join-Path $fixedAudit 'read-candidate-e'
$fixedSource=Join-Path $fixedBuild 'UltraPilot161ReadCandidate.dll'
$fixedPlugins='C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\plugins'
$fixedTarget=Join-Path $fixedPlugins 'UltraPilot161ReadCandidate.dll'
$fixedGame='C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\eurotrucks2.exe'
$fixedSettings='C:\Users\PC\AppData\Local\Programs\UltraPilot\settings.json'
$fixedInstallReceipt=Join-Path $fixedAudit 'candidate-e-install-receipt.json'
$fixedExpected='cd5cabf8bbb55ee257c56ce9aa24442f14479bfe110207976911305e1dc5575c'
function Assert-FixedAppsStopped {
 if(@(Get-CimInstance Win32_Process -Filter "Name='eurotrucks2.exe' OR Name LIKE 'UltraPilot%'").Count){throw 'Close ETS2 and UltraPilot; nothing copied'}
}
Assert-FixedAppsStopped
if(!(Test-Path -LiteralPath $fixedPlugins -PathType Container)){throw 'Exact plugins folder missing'}
if(Test-Path -LiteralPath $fixedTarget){throw 'Candidate exists; refusing overwrite'}
if(Test-Path -LiteralPath $fixedInstallReceipt){throw 'Install receipt exists; inspect instead of repeating'}
$fixedReceipt=Get-Content -LiteralPath (Join-Path $fixedBuild 'build-receipt.json') -Raw | ConvertFrom-Json
$fixedVerification=Get-Content -LiteralPath (Join-Path $fixedBuild 'verification\result.json') -Raw | ConvertFrom-Json
$fixedRegression=Get-Content -LiteralPath (Join-Path $fixedBuild 'sentinel-regression-v2\result.json') -Raw | ConvertFrom-Json
if($fixedReceipt.dll_sha256 -ne $fixedExpected -or $fixedVerification.candidate_dll_sha256 -ne $fixedExpected){throw 'Unverified DLL identity'}
if($fixedReceipt.controls_enabled -ne $false -or $fixedReceipt.isolated_mappings -ne $true -or $fixedReceipt.production_ready -ne $false){throw 'Not the isolated no-control candidate'}
if($fixedRegression.before_exception -ne 'C0000005' -or $null -ne $fixedRegression.after_exception -or
   $fixedRegression.empty_configurations -ne 15 -or $fixedRegression.nonempty_rejections -ne 3 -or
   $fixedRegression.invalid_header_rejections -ne 2){throw 'Crash regression evidence mismatch'}
if((Get-FileHash -LiteralPath (Join-Path $fixedBuild 'src\processing\traffic.cpp') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $fixedRegression.patched_source_sha256){throw 'Regression source changed'}
foreach($fixedEntry in $fixedReceipt.files.PSObject.Properties) {
 if((Get-FileHash -LiteralPath (Join-Path $fixedBuild $fixedEntry.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $fixedEntry.Value){throw ('Candidate changed: '+$fixedEntry.Name)}
}
if((Get-FileHash -LiteralPath $fixedSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $fixedExpected){throw 'DLL hash mismatch'}
if((Get-FileHash -LiteralPath $fixedGame -Algorithm SHA256).Hash.ToLowerInvariant() -ne $fixedReceipt.game_sha256){throw 'Game EXE changed; do not install'}
$fixedPreserved=[ordered]@{}
foreach($fixedFile in Get-ChildItem -LiteralPath $fixedPlugins -Filter '*.dll' -File) {
 $fixedPreserved[$fixedFile.FullName]=(Get-FileHash -LiteralPath $fixedFile.FullName -Algorithm SHA256).Hash
}
$fixedPreserved[$fixedSettings]=(Get-FileHash -LiteralPath $fixedSettings -Algorithm SHA256).Hash
Assert-FixedAppsStopped
[System.IO.File]::Copy($fixedSource,$fixedTarget,$false)
if((Get-FileHash -LiteralPath $fixedTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne $fixedExpected){throw 'Installed DLL hash mismatch'}
foreach($fixedFile in $fixedPreserved.Keys) {
 if((Get-FileHash -LiteralPath $fixedFile -Algorithm SHA256).Hash -ne $fixedPreserved[$fixedFile]){throw ('Unexpected original change: '+$fixedFile)}
}
[ordered]@{installed_candidate=$fixedTarget;dll_sha256=$fixedExpected;controls_enabled=$false;
 isolated_mappings=$true;production_ready=$false;candidate_game_verified=$false;
 fixed_fault='Candidate-d zero-size non-AI list sentinel traversal';
 previous_candidate_status='REVOKED_AND_QUARANTINED';originals_unchanged=$fixedPreserved;
 remove_only_this_file=$fixedTarget;installed_at_utc=[DateTime]::UtcNow.ToString('o')} |
 ConvertTo-Json -Depth 5 | Out-File -LiteralPath $fixedInstallReceipt -Encoding utf8
Write-Output ('INSTALLED FIXED ISOLATED TEST DLL: '+$fixedTarget)
Write-Output ('Original DLL/settings hashes preserved: '+$fixedPreserved.Count)
Write-Output 'Game verification pending; no app/game launched; controls remain disabled.'
