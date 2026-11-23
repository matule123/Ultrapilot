# Add ONLY the approved isolated read-only candidate. Never replace production.
$ErrorActionPreference='Stop'
throw 'Candidate-d is REVOKED after confirmed game crashes. Do not reinstall; see OCT24_SDK161_CANDIDATE_CRASH.md.'
$candidateRoot='C:\Users\PC\Documents\GitHub\ets2la'
$candidateAudit=Join-Path $candidateRoot 'docs\steering-audit\oct22-sdk161'
$candidateBuild=Join-Path $candidateAudit 'read-candidate-d'
$candidateSource=Join-Path $candidateBuild 'UltraPilot161ReadCandidate.dll'
$candidatePlugins='C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\plugins'
$candidateTarget=Join-Path $candidatePlugins 'UltraPilot161ReadCandidate.dll'
$candidateGame='C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\eurotrucks2.exe'
$candidateSettings='C:\Users\PC\AppData\Local\Programs\UltraPilot\settings.json'
$candidateInstallReceipt=Join-Path $candidateAudit 'candidate-d-install-receipt.json'

function Assert-CandidateAppsStopped {
 $candidateRunning=@(Get-CimInstance Win32_Process -Filter "Name='eurotrucks2.exe' OR Name LIKE 'UltraPilot%'")
 if($candidateRunning.Count){throw 'Close ETS2 and UltraPilot before adding the test DLL'}
}

Assert-CandidateAppsStopped
if(!(Test-Path -LiteralPath $candidatePlugins -PathType Container)){throw 'Exact game plugins folder not found'}
if(Test-Path -LiteralPath $candidateTarget){throw 'Candidate already exists; refusing overwrite'}
if(Test-Path -LiteralPath $candidateInstallReceipt){throw 'Install receipt already exists; inspect it instead of overwriting'}
$candidateReceipt=Get-Content -LiteralPath (Join-Path $candidateBuild 'build-receipt.json') -Raw | ConvertFrom-Json
$candidateVerification=Get-Content -LiteralPath (Join-Path $candidateBuild 'verification\result.json') -Raw | ConvertFrom-Json
if($candidateReceipt.production_ready -ne $false -or $candidateReceipt.controls_enabled -ne $false -or
   $candidateReceipt.isolated_mappings -ne $true -or $candidateReceipt.game_verified -ne $false){throw 'Expected an isolated, non-production, no-control candidate'}
$candidateExpected='2dbedf8da6479785e409163ee2755a299d509f88982ba832bec149c19c4d7add'
if($candidateReceipt.dll_sha256 -ne $candidateExpected -or $candidateVerification.candidate_dll_sha256 -ne $candidateExpected){throw 'Candidate does not match verified build'}
if((Get-FileHash -LiteralPath $candidateSource -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidateExpected){throw 'Candidate DLL hash mismatch'}
if((Get-FileHash -LiteralPath $candidateGame -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidateReceipt.game_sha256){throw 'Game EXE changed; candidate is not compatible'}
foreach($candidateEntry in $candidateReceipt.files.PSObject.Properties) {
 $candidateFile=Join-Path $candidateBuild $candidateEntry.Name
 if((Get-FileHash -LiteralPath $candidateFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidateEntry.Value){throw ('Verified source changed: '+$candidateEntry.Name)}
}

$candidatePreserved=[ordered]@{}
foreach($candidateFile in Get-ChildItem -LiteralPath $candidatePlugins -Filter '*.dll' -File) {
 $candidatePreserved[$candidateFile.FullName]=(Get-FileHash -LiteralPath $candidateFile.FullName -Algorithm SHA256).Hash
}
$candidatePreserved[$candidateSettings]=(Get-FileHash -LiteralPath $candidateSettings -Algorithm SHA256).Hash
Assert-CandidateAppsStopped
# File.Copy(..., false) refuses an existing destination, including race-created files.
[System.IO.File]::Copy($candidateSource,$candidateTarget,$false)
if((Get-FileHash -LiteralPath $candidateTarget -Algorithm SHA256).Hash.ToLowerInvariant() -ne $candidateExpected){throw 'Installed candidate failed integrity verification'}
foreach($candidateFile in $candidatePreserved.Keys) {
 if((Get-FileHash -LiteralPath $candidateFile -Algorithm SHA256).Hash -ne $candidatePreserved[$candidateFile]){throw ('Unexpected existing file change: '+$candidateFile)}
}
$candidateOutput=[ordered]@{
 installed_candidate=$candidateTarget
 dll_sha256=$candidateExpected
 game_sha256=$candidateReceipt.game_sha256
 approved_action='Add isolated diagnostic DLL only; do not replace production or enable controls'
 controls_enabled=$false
 isolated_mappings=$true
 production_ready=$false
 candidate_game_verified=$false
 originals_unchanged=$candidatePreserved
 remove_only_this_file=$candidateTarget
 installed_at_utc=[DateTime]::UtcNow.ToString('o')
}
$candidateOutput | ConvertTo-Json -Depth 5 | Out-File -LiteralPath $candidateInstallReceipt -Encoding utf8
Write-Output ('INSTALLED ISOLATED TEST DLL ONLY: '+$candidateTarget)
Write-Output ('Existing DLLs/settings preserved: '+$candidatePreserved.Count)
Write-Output 'No game/app launched, no controls enabled, no production map changed.'
