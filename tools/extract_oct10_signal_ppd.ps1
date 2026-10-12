# Read-only extraction with already available pinned TruckLib packages.
# No game, converter, download, plugin load or installation mutation.
param(
    [string]$Archive = 'C:/Program Files (x86)/Steam/steamapps/common/Euro Truck Simulator 2/base.scs',
    [Parameter(Mandatory=$true)][string]$OutputPath,
    [string]$NugetRoot = "$env:USERPROFILE/.nuget/packages"
)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath $OutputPath) { throw 'Refusing to overwrite an existing audit output' }
$auditLibraries = @(
    'trucklib.core/0.3.0/lib/net10.0/TruckLib.Core.dll',
    'gisdeflate/1.0.2/lib/netstandard2.1/GisDeflate.dll',
    'trucklib.hashfs/0.2.6/lib/net10.0/TruckLib.HashFs.dll',
    'trucklib.models/0.4.2/lib/net10.0/TruckLib.Models.dll'
)
$auditHashes = [ordered]@{}
foreach ($auditLibrary in $auditLibraries) {
    $auditLibraryPath = Join-Path $NugetRoot $auditLibrary
    $auditHashes[$auditLibrary] = (Get-FileHash -LiteralPath $auditLibraryPath -Algorithm SHA256).Hash.ToLowerInvariant()
    [Reflection.Assembly]::LoadFrom($auditLibraryPath) | Out-Null
}
$auditEntryPath = 'prefab2/cross_temp/blkw/blkw_r2_x_r1_t_narrow_tmpl.ppd'
$auditReader = [TruckLib.HashFs.HashFsReader]::Open($Archive)
try {
    $auditEntry = $auditReader.GetEntry($auditEntryPath)
    [byte[]]$auditBytes = $auditReader.Extract($auditEntry, $auditEntryPath)[0]
    $auditPpd = [TruckLib.Models.Ppd.PrefabDescriptor]::Load($auditBytes)
    $auditResult = [ordered]@{
        archive = (Resolve-Path -LiteralPath $Archive).Path
        entry = $auditEntryPath
        ppd_sha256 = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($auditBytes)).ToLowerInvariant()
        parser_hashes = $auditHashes
        version = $auditPpd.Version
        historical_package_identity_verified = $false
        nodes = @($auditPpd.Nodes | Select-Object Position,Direction)
        semaphores = @($auditPpd.Semaphores | Select-Object Position,Rotation,Type,SemaphoreId,Profile)
        curves = @($auditPpd.NavCurves | Select-Object StartPosition,EndPosition,StartRotation,EndRotation,SemaphoreId)
    }
    $auditEncoded = $auditResult | ConvertTo-Json -Depth 15
    [IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath), $auditEncoded, [Text.UTF8Encoding]::new($false))
    Write-Output "PPD $($auditResult.version), $($auditResult.semaphores.Count) authored objects, $($auditResult.curves.Count) curves; $($auditResult.ppd_sha256)"
} finally {
    $auditReader.Dispose()
}
