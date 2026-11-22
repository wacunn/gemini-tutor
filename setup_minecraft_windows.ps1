# Automatic Windows 11/10 Setup for Minecraft + Gemini Tutor Earned-Time Gating
#   irm https://raw.githubusercontent.com/wacunn/gemini-tutor/main/setup_minecraft_windows.ps1 | iex
#
# Safe to run again anytime:
# 1. Installs or updates Gemini Tutor in $HOME\GeminiTutor (preserving data\ and .env)
# 2. Installs Prism Launcher + Java 21 automatically via Windows `winget` (and also supports Official Minecraft / Bedrock)
# 3. Enables Minecraft earned-writing-time gating in data\learner.json
# 4. Adds a silent Windows Startup watchdog (`pythonw.exe`) + gated Desktop shortcut so time limits work automatically from login
# 5. Opens Prism Launcher in unlocked Parent Setup mode if Microsoft sign-in / first instance creation is still needed

$ErrorActionPreference = "Stop"
$Repo = if ($env:TUTOR_REPO) { $env:TUTOR_REPO } else { "wacunn/gemini-tutor" }
$Dir  = if ($env:TUTOR_DIR)  { $env:TUTOR_DIR }  else { Join-Path $HOME "GeminiTutor" }
$Port = if ($env:PORT)       { $env:PORT }       else { "8787" }

function Write-Step($msg) {
    Write-Host "`n$msg" -ForegroundColor Cyan
}

Write-Step "Setting up Minecraft + Gemini Tutor Earned-Time Gating on Windows..."

# 1) Ensure Gemini Tutor is installed & updated (without opening browser mid-setup)
Write-Step "Step 1 of 5: Ensuring Gemini Tutor is installed & up to date in $Dir..."
if (-not $env:TUTOR_SKIP_UPDATE) {
    $PrevNoLaunch = $env:TUTOR_NO_LAUNCH
    $env:TUTOR_NO_LAUNCH = "1"
    try {
        $InstallScript = Invoke-RestMethod -Uri "https://raw.githubusercontent.com/$Repo/main/install.ps1"
        Invoke-Expression $InstallScript
    } finally {
        $env:TUTOR_NO_LAUNCH = $PrevNoLaunch
    }
}

$VenvPy  = Join-Path $Dir ".venv\Scripts\python.exe"
$VenvPyw = Join-Path $Dir ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $VenvPyw)) { $VenvPyw = $VenvPy }

# Helper to find Prism Launcher executable
function Find-PrismExe {
    $Candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\PrismLauncher\prismlauncher.exe"),
        (Join-Path $env:ProgramFiles "PrismLauncher\prismlauncher.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "PrismLauncher\prismlauncher.exe"),
        (Join-Path $HOME "scoop\apps\prismlauncher\current\prismlauncher.exe")
    )
    foreach ($c in $Candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    $cmd = Get-Command prismlauncher.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

# 2) Install Prism Launcher + Java 21 via winget if Prism isn't installed yet
Write-Step "Step 2 of 5: Checking Minecraft (Prism Launcher & Java 21)..."
$PrismExe = Find-PrismExe
$Winget = Get-Command winget.exe -ErrorAction SilentlyContinue

if (-not $PrismExe -and $Winget -and (-not $env:TUTOR_SKIP_PRISM_INSTALL)) {
    Write-Host "Installing Prism Launcher via winget..." -ForegroundColor White
    & winget.exe install --id PrismLauncher.PrismLauncher -e --source winget --accept-package-agreements --accept-source-agreements --silent
    $PrismExe = Find-PrismExe

    # Ensure Java 21 JRE is available for modern Minecraft (1.20.5 / 1.21+)
    $HasJava21 = $false
    $AdoptiumDir = Join-Path $env:ProgramFiles "Eclipse Adoptium"
    if (Test-Path $AdoptiumDir) {
        $Jre21 = Get-ChildItem -Path $AdoptiumDir -Directory -Filter "*21*" -ErrorAction SilentlyContinue
        if ($Jre21) { $HasJava21 = $true }
    }
    if (-not $HasJava21) {
        Write-Host "Installing Java 21 runtime (for Minecraft 1.21+) via winget..." -ForegroundColor White
        & winget.exe install --id EclipseAdoptium.Temurin.21.JRE -e --source winget --accept-package-agreements --accept-source-agreements --silent
    }
} elseif ($PrismExe) {
    Write-Host "Prism Launcher already installed at: $PrismExe" -ForegroundColor Green
} else {
    Write-Host "Note: winget not found; if Official Minecraft Launcher or Bedrock is installed, Gemini Tutor will detect and gate it automatically." -ForegroundColor Yellow
}

# 3) Enable Minecraft rewards + Windows Startup Watchdog + Gated Desktop Shortcut
Write-Step "Step 3 of 5: Linking Windows Startup watchdog & Desktop shortcut gating..."
$PyConfigure = @"
import json, pathlib, sys
sys.path.insert(0, r'$Dir')
from tutor import arcade
from tutor.record import load_learner, save_learner

rec = load_learner()
arc = arcade.ensure_arcade(rec)
arc['enabled'] = True
arc['gate_minecraft'] = True
save_learner(rec)
arcade.sync_minecraft_desktop_gate(True)
inst = arcade.list_minecraft_instances()
print(json.dumps({
    'flavor': arcade.minecraft_flavor(),
    'instances': len(inst.get('instances') or []),
}))
"@

$CfgOut = $PyConfigure | & $VenvPy -
$CfgJson = $CfgOut | Select-Object -Last 1 | ConvertFrom-Json

# 4) Start Gemini Tutor background supervisor & Minecraft watchdog silently
Write-Step "Step 4 of 5: Starting Gemini Tutor background supervisor (port $Port)..."
Start-Process -FilePath $VenvPyw -ArgumentList "`"$(Join-Path $Dir 'launch.py')`" --no-open" -WorkingDirectory $Dir

$ServerReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $vr = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/version" -TimeoutSec 1
        if ($vr.version) { $ServerReady = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}

# 5) Check if first-time Microsoft account login & Minecraft instance creation are needed
Write-Step "Step 5 of 5: Verifying Minecraft instance setup..."
if ($CfgJson.flavor -eq "prism" -and $CfgJson.instances -eq 0) {
    Write-Host "`nAlmost done — One-Time Parent Sign-In Inside Prism Launcher:" -ForegroundColor Yellow
    Write-Host "  1. In the Prism Launcher window opening now, click 'Accounts' (top-right) -> 'Manage Accounts' -> 'Add Microsoft' and sign in."
    Write-Host "  2. Click 'Add Instance' (top-left) -> pick your child's Minecraft version (e.g. latest release) -> click 'OK'."
    Write-Host "  3. Double-click the new instance once so Minecraft finishes its first-time download, then close Minecraft & Prism Launcher."
    Write-Host "  After that, Minecraft is automatically gated by earned solid writing time in Gemini Tutor!" -ForegroundColor Green
    Write-Host "  • Parent settings & bonus controls: http://localhost:$Port/parent`n"
    if (-not $env:TUTOR_NO_LAUNCH) {
        try {
            Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/arcade/minecraft-parent-setup" | Out-Null
        } catch {
            if ($PrismExe) { Start-Process -FilePath $PrismExe }
        }
    }
} elseif ($CfgJson.flavor) {
    Write-Host "`nDone! Minecraft ($($CfgJson.flavor)) is linked and time-gated by Gemini Tutor." -ForegroundColor Green
    Write-Host "  • Background watchdog starts automatically whenever Windows logs in."
    Write-Host "  • Parent reward rules & bonus minutes: http://localhost:$Port/parent"
    Write-Host "  • Opening Gemini Tutor now..."
    if (-not $env:TUTOR_NO_LAUNCH) {
        Start-Process -FilePath $VenvPyw -ArgumentList "`"$(Join-Path $Dir 'launch.py')`"" -WorkingDirectory $Dir
    }
} else {
    Write-Host "`nGemini Tutor watchdog is ready! Install Minecraft Launcher from the Microsoft Store or Prism Launcher anytime, and Gemini Tutor will detect and gate it automatically." -ForegroundColor Yellow
}
