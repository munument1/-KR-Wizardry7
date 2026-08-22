param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
$sourceDir = Join-Path $workspace "src\winmm_proxy"
$outputDir = Join-Path $workspace "outputs\winmm_proxy"
$vcvars = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat"

if (-not (Test-Path -LiteralPath $vcvars)) {
    throw "Visual Studio x86 build environment not found: $vcvars"
}

New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
$source = Join-Path $sourceDir "winmm_proxy.cpp"
$definition = Join-Path $sourceDir "winmm_proxy.def"

$compile = 'call "{0}" >nul && cl /nologo /std:c++17 /O2 /EHsc /MD /LD "{1}" /link /DEF:"{2}" /OUT:"{3}" /PDB:"{4}"' -f `
    $vcvars, $source, $definition, (Join-Path $outputDir "winmm.dll"), (Join-Path $outputDir "winmm.pdb")

Push-Location $outputDir
try {
    & $env:ComSpec /d /s /c $compile
    if ($LASTEXITCODE -ne 0) {
        throw "x86 proxy build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Get-Item -LiteralPath (Join-Path $outputDir "winmm.dll")
$fontOutput = Join-Path $outputDir "wizardry7_ksx1001_8x8.bin"
$galmuri7 = Join-Path $workspace "downloads\galmuri7-8x8\font-007242d37349daf3.bin"

if (Test-Path -LiteralPath $galmuri7) {
    Copy-Item -LiteralPath $galmuri7 -Destination $fontOutput -Force
} else {
    throw "Galmuri7 8x8 source not found under downloads"
}
Get-Item -LiteralPath (Join-Path $outputDir "wizardry7_ksx1001_8x8.bin")
