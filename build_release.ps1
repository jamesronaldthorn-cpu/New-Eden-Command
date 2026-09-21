$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$Version = (Get-Content .\VERSION -Raw).Trim()
if (-not $Version) { throw 'VERSION is empty.' }
Write-Host "Building New Eden Command v$Version" -ForegroundColor Cyan

function Test-Python313Executable([string]$Path, [string[]]$PrefixArgs = @()) {
    if (-not $Path) { return $null }
    try {
        $out = & $Path @PrefixArgs -c "import sys; print(sys.executable); raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 13)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $resolved = ($out | Select-Object -First 1).ToString().Trim()
            if ($resolved -and (Test-Path $resolved)) { return $resolved }
        }
    } catch {}
    return $null
}

function Find-Python313 {
    # Release builds are intentionally pinned to CPython 3.13. The application
    # is a Windows desktop binary, so silently picking a newer interpreter can
    # change its runtime DLL requirements on end-user PCs.
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCmd) {
        try {
            $out = & $pyCmd.Source -3.13 -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) {
                $candidate = ($out | Select-Object -Last 1).ToString().Trim()
                $working = Test-Python313Executable $candidate
                if ($working) { return $working }
            }
        } catch {}
    }

    foreach ($name in @('python','python3')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd -and $cmd.Source) {
            $candidate = Test-Python313Executable $cmd.Source
            if ($candidate) { return $candidate }
        }
    }

    $candidatePaths = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'Python313\python.exe' }),
        $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'Python313\python.exe' })
    ) | Where-Object { $_ }
    foreach ($candidatePath in $candidatePaths) {
        if (Test-Path $candidatePath) {
            $working = Test-Python313Executable $candidatePath
            if ($working) { return $working }
        }
    }
    return $null
}

$PythonExe = Find-Python313
if (-not $PythonExe) {
    Write-Host 'CPython 3.13 is required for release builds. Asking winget to install Python 3.13...' -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Python 3.13 is required to build the release. Install Python 3.13 x64, then run BUILD_RELEASE.bat again.'
    }
    & winget install --id Python.Python.3.13 -e --scope user --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget returned exit code $LASTEXITCODE. Re-checking for Python 3.13..." -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 2
    $PythonExe = Find-Python313
}
if (-not $PythonExe) {
    throw 'A working CPython 3.13 installation could not be found. Install Python 3.13 x64 from python.org/winget, reopen PowerShell, and rerun BUILD_RELEASE.bat.'
}
Write-Host "Using pinned release Python: $PythonExe" -ForegroundColor DarkGray

$Venv = Join-Path $PSScriptRoot '.buildenv'
$BuildPython = Join-Path $Venv 'Scripts\python.exe'

# A venv launcher remains on disk even if its base Python was uninstalled or moved.
# Validate the venv by actually executing it; rebuild stale/broken environments automatically.
$VenvOkay = $false
if (Test-Path $BuildPython) {
    try {
        & $BuildPython -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 13)" *> $null
        if ($LASTEXITCODE -eq 0) { $VenvOkay = $true }
    } catch { $VenvOkay = $false }
}
if (-not $VenvOkay) {
    if (Test-Path $Venv) {
        Write-Host 'Existing build environment is stale or broken; recreating it...' -ForegroundColor Yellow
        Remove-Item -Recurse -Force $Venv -ErrorAction SilentlyContinue
    }
    & $PythonExe -m venv $Venv
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $BuildPython)) {
        throw 'Could not create the Python build environment.'
    }
}

& $BuildPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Failed to upgrade pip in the build environment.' }
& $BuildPython -m pip install 'pyinstaller>=6.22,<7'
if ($LASTEXITCODE -ne 0) { throw 'Failed to install PyInstaller in the build environment.' }

Remove-Item -Recurse -Force .\dist, .\build\pyinstaller -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force .\dist, .\build, .\releases | Out-Null

# End-user EVE SSO is preconfigured at build time. PKCE desktop Client IDs are
# public identifiers; never put a CCP client secret in this project.
$DeveloperSettingsPath = Join-Path $PSScriptRoot 'developer_settings.local.json'
$ClientId = $env:EVE_SSO_CLIENT_ID
$RedirectUri = $env:EVE_SSO_REDIRECT_URI
if (Test-Path $DeveloperSettingsPath) {
    try {
        $DevSettings = Get-Content $DeveloperSettingsPath -Raw | ConvertFrom-Json
        if (-not $ClientId) { $ClientId = [string]$DevSettings.eve_sso_client_id }
        if (-not $RedirectUri) { $RedirectUri = [string]$DevSettings.eve_sso_redirect_uri }
    } catch {
        throw "developer_settings.local.json is not valid JSON: $($_.Exception.Message)"
    }
}
if (-not $ClientId) {
    $ClientId = Read-Host 'Enter the CCP EVE SSO Client ID to embed in this release'
}
if (-not $ClientId) { throw 'A CCP EVE SSO Client ID is required to build a distributable release.' }
if (-not $RedirectUri) { $RedirectUri = 'http://127.0.0.1:8765/callback' }
$SavedSettings = [ordered]@{
    eve_sso_client_id = $ClientId.Trim()
    eve_sso_redirect_uri = $RedirectUri.Trim()
}
$SavedSettings | ConvertTo-Json | Set-Content $DeveloperSettingsPath -Encoding utf8
$BundledSsoPath = Join-Path $PSScriptRoot 'build\_eve_sso.json'
$SavedSettings | ConvertTo-Json | Set-Content $BundledSsoPath -Encoding utf8
Write-Host 'EVE SSO application settings will be embedded in the EXE (not shown to end users).' -ForegroundColor DarkGray

# PyInstaller resolves relative --add-data paths relative to the generated .spec file.
# Because our .spec lives under .\build, all bundled source paths must be absolute.
$IconPath = Join-Path $PSScriptRoot 'assets\new_eden_command.ico'
$Logo64Path = Join-Path $PSScriptRoot 'assets\new_eden_command_64.png'
$Logo40Path = Join-Path $PSScriptRoot 'assets\new_eden_command_40.png'
$AppPath = Join-Path $PSScriptRoot 'app.py'
if (-not (Test-Path $IconPath)) { throw "Missing application icon: $IconPath" }
if (-not (Test-Path $Logo64Path)) { throw "Missing application logo: $Logo64Path" }
if (-not (Test-Path $Logo40Path)) { throw "Missing compact application logo: $Logo40Path" }
if (-not (Test-Path $BundledSsoPath)) { throw "Missing generated SSO settings: $BundledSsoPath" }
if (-not (Test-Path $AppPath)) { throw "Missing application source: $AppPath" }

# Explicitly collect CPython's app-local Visual C runtime DLLs. PyInstaller
# normally detects them, but release packages should not rely on the target PC
# already having the same VC runtime installed. This also avoids the common
# "Failed to load Python DLL ... python3xx.dll / module could not be found"
# failure where a dependency of python3xx.dll is what is actually missing.
$PythonBase = (& $BuildPython -c "import sys; print(sys.base_prefix)" | Select-Object -Last 1).ToString().Trim()
$RuntimeBinaryArgs = @()
foreach ($DllName in @('vcruntime140.dll','vcruntime140_1.dll')) {
    $DllPath = Join-Path $PythonBase $DllName
    if (Test-Path $DllPath) {
        Write-Host "Bundling runtime dependency: $DllPath" -ForegroundColor DarkGray
        $RuntimeBinaryArgs += '--add-binary'
        $RuntimeBinaryArgs += "$DllPath;."
    }
}

# Use PyInstaller onedir rather than onefile. Onefile executables unpack their
# Python runtime to a temporary _MEI directory every launch; endpoint security
# and Windows loader timing can occasionally prevent python313.dll or one of
# its dependencies from loading after an in-app update. Onedir keeps the runtime
# beside the EXE and is substantially more reliable for an auto-updating app.
# Keep the internal executable filename for seamless v3.4.3 in-app update compatibility.
& $BuildPython -m PyInstaller --noconfirm --clean --onedir --windowed @RuntimeBinaryArgs `
  --name 'EVE Jump Planner' `
  --icon $IconPath `
  --distpath (Join-Path $PSScriptRoot 'dist') `
  --workpath (Join-Path $PSScriptRoot 'build\pyinstaller') `
  --specpath (Join-Path $PSScriptRoot 'build') `
  --add-data "$BundledSsoPath;." `
  --add-data "$IconPath;assets" `
  --add-data "$Logo64Path;assets" `
  --add-data "$Logo40Path;assets" `
  $AppPath

$AppBundle = Join-Path $PSScriptRoot 'dist\EVE Jump Planner'
$Exe = Join-Path $AppBundle 'EVE Jump Planner.exe'
if (-not (Test-Path $Exe)) { throw 'PyInstaller did not create the application EXE.' }

Write-Host 'Smoke-testing frozen application runtime...' -ForegroundColor DarkGray
try {
    $Smoke = Start-Process -FilePath $Exe -ArgumentList '--build-smoke-test' -Wait -PassThru -WindowStyle Hidden
    if ($Smoke.ExitCode -ne 0) {
        throw "Frozen EXE runtime smoke test failed with exit code $($Smoke.ExitCode)."
    }
} catch {
    throw "Frozen EXE could not start successfully. The installer/update package will not be created. $($_.Exception.Message)"
}
Write-Host 'Frozen runtime smoke test passed.' -ForegroundColor Green

& $BuildPython .\tools\make_update.py --root . --mode frozen-onedir --app-dir $AppBundle --output-dir releases

function Find-InnoCompiler {
    # 1) PATH / command discovery.
    foreach ($Name in @('ISCC.exe', 'iscc.exe', 'iscc')) {
        $Cmd = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Cmd -and $Cmd.Source -and (Test-Path $Cmd.Source)) { return $Cmd.Source }
    }

    # 2) Standard per-user and per-machine install locations.
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path $env:LOCALAPPDATA 'Inno Setup 6\ISCC.exe'),
        $(if (${env:ProgramFiles(x86)}) { Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe' }),
        $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe' })
    ) | Where-Object { $_ }
    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) { return $Candidate }
    }

    # 3) Ask Windows where Inno Setup is installed. This covers winget installs
    #    whose destination differs from the common paths above.
    $RegistryRoots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($Root in $RegistryRoots) {
        $Apps = Get-ItemProperty $Root -ErrorAction SilentlyContinue |
            Where-Object { $_.DisplayName -like 'Inno Setup*' }
        foreach ($App in $Apps) {
            if ($App.InstallLocation) {
                $Candidate = Join-Path $App.InstallLocation 'ISCC.exe'
                if (Test-Path $Candidate) { return $Candidate }
            }
            if ($App.DisplayIcon) {
                $IconPath = ($App.DisplayIcon -replace ',\d+$','').Trim('"')
                if (Test-Path $IconPath) {
                    $Candidate = Join-Path (Split-Path $IconPath -Parent) 'ISCC.exe'
                    if (Test-Path $Candidate) { return $Candidate }
                }
            }
            if ($App.UninstallString) {
                $Uninstall = $App.UninstallString.Trim()
                if ($Uninstall.StartsWith('"')) {
                    $EndQuote = $Uninstall.IndexOf('"', 1)
                    if ($EndQuote -gt 1) { $Uninstall = $Uninstall.Substring(1, $EndQuote - 1) }
                } else {
                    $Uninstall = $Uninstall.Split(' ')[0]
                }
                if (Test-Path $Uninstall) {
                    $Candidate = Join-Path (Split-Path $Uninstall -Parent) 'ISCC.exe'
                    if (Test-Path $Candidate) { return $Candidate }
                }
            }
        }
    }

    # 4) Last-resort narrow search of likely Inno Setup folders only.
    $Bases = @($env:LOCALAPPDATA, $env:ProgramFiles, ${env:ProgramFiles(x86)}) |
        Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique
    foreach ($Base in $Bases) {
        $Match = Get-ChildItem -Path $Base -Directory -Filter 'Inno Setup*' -ErrorAction SilentlyContinue |
            ForEach-Object { Get-ChildItem -Path $_.FullName -Filter ISCC.exe -File -Recurse -ErrorAction SilentlyContinue } |
            Select-Object -First 1
        if ($Match) { return $Match.FullName }
    }
    return $null
}

$ISCC = Find-InnoCompiler
if (-not $ISCC) {
    Write-Host 'Inno Setup compiler was not found. Asking winget to install Inno Setup 6...' -ForegroundColor Yellow
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'Inno Setup 6 is required. Install it, then run BUILD_RELEASE.bat again.'
    }

    & winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget returned exit code $LASTEXITCODE. Re-checking for an existing Inno Setup installation..." -ForegroundColor Yellow
    }
    Start-Sleep -Seconds 1
    $ISCC = Find-InnoCompiler
}
if (-not $ISCC) {
    throw 'Inno Setup appears in winget, but ISCC.exe could not be located. Open Inno Setup once or reinstall Inno Setup 6, then rerun BUILD_RELEASE.bat.'
}

Write-Host "Using Inno Setup compiler: $ISCC" -ForegroundColor DarkGray

& $ISCC "/DMyAppVersion=$Version" .\installer\EVEJumpPlanner.iss

$Installer = Join-Path $PSScriptRoot "releases\New_Eden_Command_Setup_v$Version.exe"
$Update = Join-Path $PSScriptRoot "releases\New_Eden_Command_Update_v$Version.ejpupdate"
if (-not (Test-Path $Installer)) { throw "Installer was not created: $Installer" }
if (-not (Test-Path $Update)) { throw "Update file was not created: $Update" }

# Build a stable latest.json feed. Host it beside the installer/update files over HTTPS.
& $BuildPython .\tools\make_feed.py --root . --installer $Installer --update $Update --output releases/latest.json
$Feed = Join-Path $PSScriptRoot 'releases\latest.json'
if (-not (Test-Path $Feed)) { throw "Update feed was not created: $Feed" }

$hashes = @()
foreach ($File in @($Installer,$Update,$Feed)) {
    $h = Get-FileHash $File -Algorithm SHA256
    $hashes += "$($h.Hash.ToLower())  $([IO.Path]::GetFileName($File))"
}
$hashes | Set-Content .\releases\SHA256SUMS.txt -Encoding ascii

Write-Host ''
Write-Host 'Release ready:' -ForegroundColor Green
Write-Host "  $Installer"
Write-Host "  $Update"
Write-Host "  $Feed"
Write-Host "  $PSScriptRoot\releases\SHA256SUMS.txt"
Write-Host ''
Write-Host 'Online updater:' -ForegroundColor Cyan
Write-Host '  Host the four release files together over HTTPS.'
Write-Host '  For GitHub Releases, use this feed URL in the app:'
Write-Host '  https://github.com/OWNER/REPO/releases/latest/download/latest.json'
