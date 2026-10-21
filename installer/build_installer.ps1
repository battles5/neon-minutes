# Builds dist\TrascrittoreRiunioni-Setup-<version>.exe
#
#   powershell -ExecutionPolicy Bypass -File installer\build_installer.ps1
#
# Needs: the project's .venv (the tested dependency versions are read from it), the
# pyannote model in the Hugging Face cache (or HF_TOKEN in .env), Inno Setup 6.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$py = Join-Path $root ".venv\Scripts\python.exe"
$build = Join-Path $root "build"
$stage = Join-Path $build "stage"
$cache = Join-Path $build "cache"
$dist = Join-Path $root "dist"

# Portable CPython (python-build-standalone): includes pip and tkinter, nothing to install.
$runtimeUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/20261003/cpython-3.12.15%2B20261003-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
$runtimeSha256 = "6fba7f2ae506facf41d457ea8293c7497910a675c69a4e954875169410a50402"

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 non trovato: winget install JRSoftware.InnoSetup --scope user" }

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

function Copy-Utf8Bom($src, $dest) {
    # Inno Setup reads .iss and .txt files as UTF-8 only when they start with a BOM.
    $text = [IO.File]::ReadAllText($src, [Text.Encoding]::UTF8)
    [IO.File]::WriteAllText($dest, $text, (New-Object Text.UTF8Encoding $true))
}

$version = (& $py -c "import sys; sys.path.insert(0, r'$root'); import meeting_transcriber; print(meeting_transcriber.__version__)").Trim()
Step "Trascrittore riunioni $version"

Step "Cartella di staging"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage, $cache, $dist | Out-Null

Step "Python portatile"
$tgz = Join-Path $cache ([Uri]::UnescapeDataString((Split-Path $runtimeUrl -Leaf)))
if (-not (Test-Path $tgz)) { Invoke-WebRequest -Uri $runtimeUrl -OutFile $tgz -UseBasicParsing }
$hash = (Get-FileHash $tgz -Algorithm SHA256).Hash.ToLower()
if ($hash -ne $runtimeSha256) { Remove-Item $tgz; throw "SHA-256 del runtime Python non valido: $hash" }
tar -xzf $tgz -C $stage
if ($LASTEXITCODE) { throw "estrazione del runtime non riuscita" }
Rename-Item (Join-Path $stage "python") "runtime"
# A ._pth file fixes sys.path and puts Python in isolated mode, so a colleague's own Python
# (user site-packages, PYTHONPATH, .pth files) can never leak into the program. Without
# "import site" the user site-packages stays out; ".." makes the program importable.
[IO.File]::WriteAllText("$stage\runtime\python312._pth", "python312.zip`r`nDLLs`r`nLib`r`nLib\site-packages`r`n..`r`n")

Step "Programma, documentazione, licenze"
New-Item -ItemType Directory -Force "$stage\meeting_transcriber", "$stage\assets", "$stage\docs", "$stage\installer" | Out-Null
Copy-Item "$root\meeting_transcriber\*.py" "$stage\meeting_transcriber"
Copy-Item "$root\assets\piuma.ico", "$root\assets\piuma.png" "$stage\assets"
Copy-Item "$root\docs\*" "$stage\docs" -Recurse
Copy-Item "$root\installer\postinstall.py" "$stage\installer"
Copy-Utf8Bom "$root\LICENSE.txt" "$stage\LICENSE.txt"
Copy-Utf8Bom "$root\installer\glossary-template.txt" "$stage\glossary.txt"

Step "Modello pyannote, versioni delle dipendenze, avvisi di terze parti"
& $py (Join-Path $PSScriptRoot "prepare_stage.py") $stage
if ($LASTEXITCODE) { throw "prepare_stage.py non riuscito" }
Copy-Utf8Bom "$stage\THIRD-PARTY-NOTICES.txt" "$stage\THIRD-PARTY-NOTICES.txt"

Step "Compilazione del setup (Inno Setup)"
# Sizes measured by prepare_stage.py, in MB, so the wizard states them before installing.
$sizes = Get-Content "$stage\installer\sizes.json" -Raw | ConvertFrom-Json
function MB($bytes) { [string][math]::Ceiling($bytes / 1e6) }
$sizeDefines = @(
    "/DDlTorchCuda=$(MB $sizes.download.torch.cuda)", "/DDlTorchCpu=$(MB $sizes.download.torch.cpu)",
    "/DDlDeps=$(MB $sizes.download.deps)",
    "/DDlModelCuda=$(MB $sizes.download.whisper.cuda)", "/DDlModelCpu=$(MB $sizes.download.whisper.cpu)",
    "/DInstCuda=$(MB $sizes.installed.cuda)", "/DInstCpu=$(MB $sizes.installed.cpu)"
)
Copy-Utf8Bom "$PSScriptRoot\setup.iss" "$build\setup.iss"
Copy-Utf8Bom "$PSScriptRoot\requisiti.txt" "$build\requisiti.txt"
& $iscc "/DAppVersion=$version" "/DStage=$stage" @sizeDefines "/O$dist" "$build\setup.iss"
if ($LASTEXITCODE) { throw "ISCC non riuscito" }

$exe = Get-Item (Join-Path $dist "TrascrittoreRiunioni-Setup-$version.exe")
Step ("Fatto: {0} ({1:N0} MB)" -f $exe.FullName, ($exe.Length / 1MB))
