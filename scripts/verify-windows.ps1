<#
.SYNOPSIS
    Local verification harness for the Capital Steward Engine as a personal,
    single-user application on this Windows machine.

.DESCRIPTION
    Exercises the shipped application exactly as a user would: starts the
    backend and the interface on loopback, waits for real readiness, checks the
    golden trilogy, restarts the engine to prove run history and hysteresis
    state survive, and confirms nothing already in data\ was destroyed.

    Every result is written to a timestamped evidence directory. The script
    exits 0 only if every check passed.

    It starts nothing it does not stop, and it stops only what it started.

.NOTES
    Read-only with respect to the repository. It does NOT clone, pull,
    checkout, build, regenerate fixtures, or modify tracked files.

    It DOES append runs to data\engine.db (that is what a run does). The
    data-preservation phase proves pre-existing files and run records are still
    intact afterwards, rather than pretending nothing changed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\verify-windows.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\verify-windows.ps1 -IncludeLauncher -Verbose
#>

#Requires -Version 5.1
[CmdletBinding()]
param(
    # Repository to verify. Defaults to the parent of this script's folder.
    [string]$RepoRoot,

    # Where evidence directories are created. Defaults to the user profile so
    # the repository stays clean.
    [string]$EvidenceRoot,

    # The branch you intend to verify. Defaults to main, which is what a laptop
    # holds once this work is merged. Pass a feature-branch name to verify a PR
    # head instead.
    # The GitHub repository this checkout must come from. Both HTTPS
    # (https://github.com/owner/repo.git) and SSH (git@github.com:owner/repo.git)
    # remote forms are accepted. Verification refuses to run against a checkout
    # whose origin identifies some other repository.
    [string]$ExpectedOwner = 'ramkivs',
    [string]$ExpectedRepo  = 'CapStew-Engine',

    [string]$ExpectedBranch = 'main',

    # Optional strict pin against HEAD. Empty by default, which RECORDS the
    # commit without rejecting it. A hardcoded default SHA is self-defeating:
    # the commit that sets it changes HEAD and immediately makes it stale. The
    # substance check below is what actually catches a wrong or old checkout.
    [string]$ExpectedCommit = '',

    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173,

    # Polling budgets. Readiness is detected by polling, never by sleeping a
    # fixed amount and hoping.
    [int]$ReadyTimeoutSec   = 180,
    [int]$InstallTimeoutSec = 900,

    # Also drive scripts\start.bat and scripts\stop.bat. Off by default because
    # they open their own console windows.
    [switch]$IncludeLauncher,

    # Permit an unclean working tree (for inspecting local edits).
    [switch]$AllowDirtyTree
)

$ErrorActionPreference = 'Stop'
$ProgressPreference    = 'SilentlyContinue'

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
if (-not $RepoRoot)     { $RepoRoot     = Split-Path -Parent $PSScriptRoot }
if (-not $EvidenceRoot) { $EvidenceRoot = Join-Path $env:USERPROFILE 'CapStew-Verification' }

$RepoRoot = (Resolve-Path $RepoRoot).Path
$Stamp    = Get-Date -Format 'yyyyMMdd-HHmmss'
$Evidence = Join-Path $EvidenceRoot "verify-$Stamp"

$BackendUrl  = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"
$Api         = "$BackendUrl/api/v1"

$Venv    = Join-Path $RepoRoot '.venv'
$VenvPy  = Join-Path $Venv 'Scripts\python.exe'
$DataDir = Join-Path $RepoRoot 'data'

# Process bookkeeping: only these are ever stopped.
$script:Started        = @()
$script:CleanupResults = @()
$script:Checks         = New-Object System.Collections.ArrayList

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
function Write-Evidence {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][AllowEmptyString()][string]$Text)
    $path = Join-Path $Evidence $Name
    Set-Content -Path $path -Value $Text -Encoding UTF8
    Write-Verbose "evidence -> $Name"
}

function Save-Json {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)]$Object)
    Write-Evidence -Name $Name -Text ($Object | ConvertTo-Json -Depth 12)
}

function Add-Check {
    param([Parameter(Mandatory)][string]$Name, [Parameter(Mandatory)][bool]$Pass, [string]$Detail = '')
    $result = 'FAIL'
    if ($Pass) { $result = 'PASS' }

    [void]$script:Checks.Add([pscustomobject]@{
        Result = $result
        Check  = $Name
        Detail = $Detail
    })

    $mark = '[FAIL]'
    if ($Pass) { $mark = '[ ok ]' }
    Write-Host "  $mark $Name"
    if ($Detail) { Write-Host "         $Detail" }
}

# Polls until the endpoint answers 200, or throws. The per-attempt catch is
# part of the poll, not a swallowed failure: a timeout throws.
function Wait-ForHttp {
    param([Parameter(Mandatory)][string]$Url, [Parameter(Mandatory)][int]$TimeoutSec,
          [Parameter(Mandatory)][string]$Label)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $attempts = 0
    while ((Get-Date) -lt $deadline) {
        $attempts++
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Verbose "$Label ready after $attempts attempt(s)"
                return $response
            }
        }
        catch { Start-Sleep -Milliseconds 750 }
    }
    throw "$Label did not answer 200 at $Url within $TimeoutSec s ($attempts attempts)"
}

function Invoke-Api {
    param([Parameter(Mandatory)][string]$Path, [string]$Method = 'GET', [string]$OutFile)
    $uri = "$Api$Path"
    $response = Invoke-WebRequest -Uri $uri -Method $Method -UseBasicParsing -TimeoutSec 120
    if ($OutFile) {
        Set-Content -Path (Join-Path $Evidence $OutFile) -Value $response.Content -Encoding UTF8
    }
    return ($response.Content | ConvertFrom-Json)
}

function Get-PortOwner {
    param([Parameter(Mandatory)][int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conns) { return ($conns | Select-Object -First 1).OwningProcess }
    return $null
}

# Parses owner/repo out of an origin URL in either common Git form.
#   https://github.com/owner/repo.git      -> owner, repo
#   git@github.com:owner/repo.git          -> owner, repo
#   ssh://git@github.com/owner/repo        -> owner, repo
function Resolve-GitRemote {
    param([AllowEmptyString()][string]$Url)
    if (-not $Url) { return $null }
    $m = [regex]::Match($Url.Trim(), 'github\.com[:/]+([^/:\s]+)/([^/\s#?]+?)(?:\.git)?/?$')
    if (-not $m.Success) { return $null }
    return [pscustomobject]@{ Owner = $m.Groups[1].Value; Repo = $m.Groups[2].Value }
}

function Test-ProcessAlive {
    param([Parameter(Mandatory)][int]$ProcessId)
    $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($proc) { return $true }
    return $false
}

# Returns the taskkill exit code and output. taskkill does not throw on failure,
# so the old try/catch could never report one.
function Invoke-Taskkill {
    param([Parameter(Mandatory)][int]$ProcessId)
    $output = & taskkill.exe /PID $ProcessId /T /F 2>&1
    return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = ($output -join ' ') }
}

function Wait-ForExit {
    param([Parameter(Mandatory)]$Process, [int]$TimeoutSec = 15)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if ($Process.HasExited) { return $true }
        Start-Sleep -Milliseconds 300
    }
    return $Process.HasExited
}

# Terminates only the processes this execution started, checks the taskkill exit
# code, and confirms the process is actually gone. With -Final it also records
# the aggregate verdicts; called that way on both the success and failure paths.
function Stop-StartedProcesses {
    param([switch]$Final)

    foreach ($entry in $script:Started) {
        if (-not $entry.Process) { continue }
        $targetPid = $entry.Process.Id

        if ($entry.Process.HasExited) {
            $script:CleanupResults += [pscustomobject]@{
                Label = $entry.Label; Pid = $targetPid; Action = 'already exited'
                ExitCode = -1; Confirmed = $true
            }
            continue
        }

        Write-Host "  stopping $($entry.Label) (PID $targetPid)"
        $kill = Invoke-Taskkill -ProcessId $targetPid
        $gone = Wait-ForExit -Process $entry.Process -TimeoutSec 15
        $script:CleanupResults += [pscustomobject]@{
            Label = $entry.Label; Pid = $targetPid; Action = 'taskkill /T /F'
            ExitCode = $kill.ExitCode; Confirmed = $gone
        }
        if ($kill.ExitCode -ne 0) {
            Write-Warning "taskkill exited $($kill.ExitCode) for $($entry.Label) (PID $targetPid): $($kill.Output)"
        }
        if (-not $gone) {
            Write-Warning "$($entry.Label) (PID $targetPid) is still running after taskkill"
        }
    }
    $script:Started = @()

    $rows = @('label,pid,action,taskkill_exit_code,termination_confirmed')
    foreach ($r in $script:CleanupResults) {
        $rows += "$($r.Label),$($r.Pid),$($r.Action),$($r.ExitCode),$($r.Confirmed)"
    }
    Write-Evidence -Name '70-process-cleanup.csv' -Text ($rows -join "`r`n")

    if (-not $Final) { return }

    $attempted = @($script:CleanupResults | Where-Object { $_.Action -eq 'taskkill /T /F' })
    $badExit   = @($attempted | Where-Object { $_.ExitCode -ne 0 })
    $stillUp   = @($script:CleanupResults | Where-Object { -not $_.Confirmed })
    Add-Check -Name 'every process this execution started has terminated' `
              -Pass ($stillUp.Count -eq 0) `
              -Detail "$($script:CleanupResults.Count) tracked, $($stillUp.Count) still alive"
    Add-Check -Name 'taskkill returned 0 for every termination it attempted' `
              -Pass ($badExit.Count -eq 0) `
              -Detail "$($attempted.Count) taskkill call(s), $($badExit.Count) non-zero"
}

function Snapshot-DataDir {
    if (-not (Test-Path $DataDir)) { return @() }
    return Get-ChildItem -Path $DataDir -Recurse -File |
        ForEach-Object {
            [pscustomobject]@{
                Relative = $_.FullName.Substring($DataDir.Length + 1)
                Length   = $_.Length
                Hash     = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash
            }
        } | Sort-Object Relative
}

function Start-Service {
    param([Parameter(Mandatory)][string]$Label, [Parameter(Mandatory)][string]$FilePath,
          [Parameter(Mandatory)][string[]]$Arguments, [Parameter(Mandatory)][string]$WorkingDir,
          [Parameter(Mandatory)][string]$LogFile)

    Write-Host "  starting $Label"
    $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments `
                          -WorkingDirectory $WorkingDir -WindowStyle Hidden `
                          -RedirectStandardOutput $LogFile `
                          -RedirectStandardError "$LogFile.err" -PassThru
    $script:Started += [pscustomobject]@{ Label = $Label; Process = $proc; Log = $LogFile }
    return $proc
}

function Resolve-Python {
    if (Test-Path $VenvPy) { return $VenvPy }
    $cmd = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "No Python found. Looked for $VenvPy and python.exe on PATH. Run scripts\start.bat once to create .venv."
}

# --------------------------------------------------------------------------
# Summary writer
# --------------------------------------------------------------------------
function Write-Summary {
    param([Parameter(Mandatory)][string]$Outcome, [string]$FatalError = '')

    $passed = @($script:Checks | Where-Object { $_.Result -eq 'PASS' }).Count
    $failed = @($script:Checks | Where-Object { $_.Result -eq 'FAIL' }).Count

    $lines = @()
    $lines += "Capital Steward Engine - local verification"
    $lines += "Generated : $(Get-Date -Format 'o')"
    $lines += "Outcome   : $Outcome"
    $lines += "Repository: $RepoRoot"
    $lines += "Evidence  : $Evidence"
    $lines += "Checks    : $passed passed, $failed failed, $($script:Checks.Count) total"
    $lines += ""
    if ($FatalError) {
        $lines += "FATAL: $FatalError"
        $lines += ""
    }
    $lines += "{0,-6} {1}" -f 'RESULT', 'CHECK'
    $lines += ("-" * 78)
    foreach ($check in $script:Checks) {
        $lines += "{0,-6} {1}" -f $check.Result, $check.Check
        if ($check.Detail) { $lines += "       $($check.Detail)" }
    }
    $lines += ""
    $lines += "Processes started by this script: $($script:Started.Count)"
    foreach ($entry in $script:Started) {
        $pid2 = 'n/a'
        if ($entry.Process) { $pid2 = $entry.Process.Id }
        $lines += "  - $($entry.Label) (PID $pid2) log: $($entry.Log)"
    }

    $text = ($lines -join "`r`n")
    Write-Evidence -Name '00-summary.txt' -Text $text
    Write-Host ""
    Write-Host $text
}

# ==========================================================================
# Main
# ==========================================================================
New-Item -ItemType Directory -Path $Evidence -Force | Out-Null
Write-Host "Capital Steward Engine - local verification"
Write-Host "Repository : $RepoRoot"
Write-Host "Evidence   : $Evidence"
Write-Host ""

try {
    # ---------------------------------------------------------------- 1. repo
    Write-Host "[1/9] Repository state"

    if (-not (Test-Path (Join-Path $RepoRoot 'app\main.py'))) {
        throw "$RepoRoot does not look like a Capital Steward Engine checkout (app\main.py missing)"
    }

    $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD).Trim()
    $commit = (& git -C $RepoRoot rev-parse HEAD).Trim()
    $dirty  = (& git -C $RepoRoot status --porcelain)
    $remote = (& git -C $RepoRoot config --get remote.origin.url)

    $engineLine = (Select-String -Path (Join-Path $RepoRoot 'app\config.py') -Pattern '^ENGINE_VERSION').Line
    $gitText = "branch : $branch`r`ncommit : $commit`r`nremote : $remote`r`n$engineLine`r`n`r`nstatus --porcelain:`r`n$($dirty -join "`r`n")"
    Write-Evidence -Name '02-git-state.txt' -Text $gitText

    # Identity gate: refuse to verify some other repository's checkout. Both
    # HTTPS and SSH remote forms are understood by Resolve-GitRemote.
    if (-not $remote) { throw "No origin remote is configured in $RepoRoot." }

    $ident = Resolve-GitRemote -Url $remote
    $identText = 'unrecognised remote format'
    if ($ident) { $identText = "$($ident.Owner)/$($ident.Repo)" }
    Write-Evidence -Name '02b-origin-identity.txt' -Text "origin url   : $remote`r`norigin ident : $identText`r`nexpected     : $ExpectedOwner/$ExpectedRepo"

    Add-Check -Name "origin identifies $ExpectedOwner/$ExpectedRepo" -Pass ($null -ne $ident) -Detail "origin: $remote"
    if (-not $ident) {
        throw "Could not parse the origin remote '$remote'. Expected an HTTPS or SSH github.com URL for $ExpectedOwner/$ExpectedRepo."
    }

    $sameRepo = ($ident.Owner -ieq $ExpectedOwner) -and ($ident.Repo -ieq $ExpectedRepo)
    if (-not $sameRepo) {
        throw "origin identifies $identText, not $ExpectedOwner/$ExpectedRepo. Refusing to run verification against an unrelated repository."
    }
    Write-Host "  origin verified: $identText"
    Add-Check -Name "branch is $ExpectedBranch" -Pass ($branch -eq $ExpectedBranch) -Detail "actual: $branch"

    $pinned = $false
    if ($ExpectedCommit) { $pinned = $commit.StartsWith($ExpectedCommit) }
    if ($ExpectedCommit) {
        Add-Check -Name "commit starts with $ExpectedCommit" -Pass $pinned -Detail "actual: $commit"
    }
    if (-not $ExpectedCommit) {
        Add-Check -Name 'commit recorded (no -ExpectedCommit pin supplied)' `
                  -Pass ($commit.Length -ge 7) -Detail "HEAD: $commit"
    }

    # Substance check. A SHA cannot be pinned by default without going stale the
    # moment it is committed, so verify the checkout actually CARRIES this
    # release instead: the engine version stamp plus the v1.2 artefacts. This
    # rejects an old or wrong checkout without depending on an unknowable SHA.
    $configPath = Join-Path $RepoRoot 'app\config.py'
    $configText = Get-Content -Raw -Path $configPath
    $versionOk = $configText -match 'ENGINE_VERSION\s*=\s*"1\.2\.0"'
    Add-Check -Name 'checkout carries the v1.2 engine (ENGINE_VERSION 1.2.0)' -Pass $versionOk `
              -Detail 'supply -ExpectedCommit <sha> to pin an exact release'

    $harness = Test-Path (Join-Path $RepoRoot 'scripts\verify-windows.ps1')
    $guide   = Test-Path (Join-Path $RepoRoot 'docs\WINDOWS-VERIFICATION.md')
    Add-Check -Name 'v1.2 verification artefacts present' -Pass ($harness -and $guide)

    $clean = (@($dirty).Count -eq 0)
    if (-not $clean) {
        Write-Warning "working tree has $(@($dirty).Count) uncommitted change(s)"
        if (-not $AllowDirtyTree) {
            throw "Working tree is not clean. Commit or stash first, or re-run with -AllowDirtyTree."
        }
    }
    Add-Check -Name 'working tree is clean' -Pass $clean -Detail "$(@($dirty).Count) modified path(s)"

    # ------------------------------------------------------- 2. prerequisites
    Write-Host ""
    Write-Host "[2/9] Prerequisites and port availability"

    $env2 = @()
    $env2 += "OS      : $([System.Environment]::OSVersion.VersionString)"
    $env2 += "PSVersion: $($PSVersionTable.PSVersion)"
    $env2 += "Machine : $env:COMPUTERNAME"
    $env2 += "User    : $env:USERNAME"

    $python = $null
    try {
        $python = Resolve-Python
        $pyVer = (& $python --version 2>&1)
        $env2 += "Python  : $python ($pyVer)"
    }
    catch { $env2 += "Python  : NOT FOUND - $($_.Exception.Message)" }

    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($node) { $env2 += "Node    : $(& node.exe --version)" }
    if (-not $node) { $env2 += "Node    : NOT FOUND" }

    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npm) { $env2 += "npm     : $(& npm.cmd --version)" }
    if (-not $npm) { $env2 += "npm     : NOT FOUND" }

    Write-Evidence -Name '01-environment.txt' -Text ($env2 -join "`r`n")
    Write-Host ($env2 -join "`r`n")

    Add-Check -Name 'Python available'     -Pass ($null -ne $python) -Detail "$python"
    Add-Check -Name 'Node available'       -Pass ($null -ne $node)
    Add-Check -Name 'npm available'        -Pass ($null -ne $npm)
    Add-Check -Name 'frontend deps present' -Pass (Test-Path (Join-Path $RepoRoot 'frontend\node_modules')) `
              -Detail 'run scripts\start.bat once if missing'

    if (-not $python) { throw 'Python is required to run the backend.' }
    if (-not $npm)    { throw 'npm is required to run the interface.' }
    if (-not (Test-Path (Join-Path $RepoRoot 'frontend\node_modules'))) {
        throw 'frontend\node_modules is missing. Run scripts\start.bat once to install, then re-run.'
    }

    $portFree = $true
    $portText = @()
    foreach ($port in @($BackendPort, $FrontendPort)) {
        $owner = Get-PortOwner -Port $port
        $line = "port $port : free"
        if ($owner) { $line = "port $port : IN USE by PID $owner" }
        $portText += $line
        if ($owner) { $portFree = $false }
    }
    Write-Evidence -Name '03-ports.txt' -Text ($portText -join "`r`n")
    Add-Check -Name "ports $BackendPort/$FrontendPort are free" -Pass $portFree -Detail ($portText -join '; ')
    if (-not $portFree) { throw 'Free the listed ports (scripts\stop.bat) and re-run.' }

    # ------------------------------------------------------- 3. data snapshot
    Write-Host ""
    Write-Host "[3/9] Snapshot of existing user data"

    $before = @(Snapshot-DataDir)
    $beforeText = "files in data\ before: $($before.Count)"
    foreach ($item in $before) { $beforeText += "`r`n  $($item.Relative)  $($item.Length) bytes  $($item.Hash)" }
    Write-Evidence -Name '50-data-before.txt' -Text $beforeText
    Write-Host "  $($before.Count) existing file(s) in data\"

    $runsBefore = @()
    $policyBefore = $null

    # ------------------------------------------------- 4. start the services
    Write-Host ""
    Write-Host "[4/9] Starting the engine and the interface"

    $backendLog  = Join-Path $Evidence '10-backend.log'
    $frontendLog = Join-Path $Evidence '11-frontend.log'

    [void](Start-Service -Label 'backend' -FilePath $python `
        -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
        -WorkingDir $RepoRoot -LogFile $backendLog)

    [void](Start-Service -Label 'frontend' -FilePath 'cmd.exe' `
        -Arguments @('/c', "npm run dev -- --host 127.0.0.1 --port $FrontendPort") `
        -WorkingDir (Join-Path $RepoRoot 'frontend') -LogFile $frontendLog)

    # ------------------------------------------------------- 5. readiness
    Write-Host ""
    Write-Host "[5/9] Waiting for readiness, then checking health, UI and proxy"

    [void](Wait-ForHttp -Url "$Api/health" -TimeoutSec $ReadyTimeoutSec -Label 'backend')
    Add-Check -Name 'backend /health answers 200' -Pass $true

    $health = Invoke-Api -Path '/health' -OutFile '20-health.json'
    Add-Check -Name 'engine reports status ok' -Pass ($health.status -eq 'ok') -Detail "engine_version=$($health.engine_version)"

    [void](Wait-ForHttp -Url $FrontendUrl -TimeoutSec $ReadyTimeoutSec -Label 'interface')
    $index = Invoke-WebRequest -Uri $FrontendUrl -UseBasicParsing -TimeoutSec 30
    Set-Content -Path (Join-Path $Evidence '21-ui-index.html') -Value $index.Content -Encoding UTF8
    Add-Check -Name 'interface serves the app shell' -Pass ($index.Content -match 'id="root"')

    $proxy = Invoke-WebRequest -Uri "$FrontendUrl/api/v1/health" -UseBasicParsing -TimeoutSec 30
    $proxyJson = $proxy.Content | ConvertFrom-Json
    Save-Json -Name '22-proxy-health.json' -Object $proxyJson
    Add-Check -Name 'dev server proxies /api to the engine' -Pass ($proxyJson.status -eq 'ok') `
              -Detail "via $FrontendUrl -> $BackendUrl"

    # ------------------------------------------------ 5b. existing history
    # Snapshot EVERY run that already exists before this script creates one.
    # Those runs belong to the user; each must still be present afterwards.
    $originalRuns = @(Invoke-Api -Path '/runs' -OutFile '39-runs-original.json')
    $originalRunIds = @($originalRuns | ForEach-Object { $_.run_id } | Where-Object { $_ })
    $origLines = @("pre-existing run_id(s): $($originalRunIds.Count)")
    foreach ($id in $originalRunIds) { $origLines += "  $id" }
    Write-Evidence -Name '39b-original-run-ids.txt' -Text ($origLines -join "`r`n")
    Write-Host "  pre-existing runs recorded: $($originalRunIds.Count)"

    # --------------------------------------------------- 6. golden trilogy
    Write-Host ""
    Write-Host "[6/9] Golden trilogy"

    $run1 = Invoke-Api -Path '/run-sample' -Method POST -OutFile '30-run-1.json'
    $runId1 = $run1.run_id
    Write-Host "  run 1: $runId1 ($(@($run1.holdings).Count) holdings)"

    $expected = @{
        'Salasar Techno Engg' = @('TRIM', 'G2')
        'Ashoka Buildcon'     = @('EXIT', 'G1')
        'Larsen & Toubro'     = @('HOLD', 'G3')
    }

    $trilogyLines = @()
    $trilogyOk = $true
    foreach ($name in $expected.Keys) {
        $holding = @($run1.holdings | Where-Object { $_.instrument -eq $name })
        if ($holding.Count -ne 1) {
            $trilogyOk = $false
            $trilogyLines += "$name : NOT FOUND in payload"
            continue
        }
        $want = $expected[$name]
        $gotDecision = $holding[0].decision
        $gotGate     = $holding[0].stage1.winning_gate
        $match = ($gotDecision -eq $want[0]) -and ($gotGate -eq $want[1])
        if (-not $match) { $trilogyOk = $false }
        $mark = 'MISMATCH'
        if ($match) { $mark = 'ok' }
        $trilogyLines += "$name : $gotDecision/$gotGate expected $($want[0])/$($want[1]) [$mark]"
    }
    Write-Evidence -Name '31-golden-trilogy.txt' -Text ($trilogyLines -join "`r`n")
    foreach ($line in $trilogyLines) { Write-Host "  $line" }
    Add-Check -Name 'SALASAR -> TRIM/G2, ASHOKA -> EXIT/G1, LT -> HOLD/G3' -Pass $trilogyOk

    # --------------------------------------- 7. restart, history, diff
    Write-Host ""
    Write-Host "[7/9] Restart: history, previous-run recovery, diff"

    $runsPre = @(Invoke-Api -Path '/runs' -OutFile '40-runs-before-restart.json')
    Save-Json -Name '41-runs-before-restart-parsed.json' -Object $runsPre
    Add-Check -Name 'run 1 is listed in history' -Pass (@($runsPre | Where-Object { $_.run_id -eq $runId1 }).Count -eq 1)

    $policyPre = Invoke-Api -Path '/policy' -OutFile '42-policy-before-restart.json'

    $backendEntry = $script:Started | Where-Object { $_.Label -eq 'backend' } | Select-Object -First 1
    $restartKill = Invoke-Taskkill -ProcessId $backendEntry.Process.Id
    $restarted   = Wait-ForExit -Process $backendEntry.Process -TimeoutSec 30
    # Record it with the rest so the final cleanup verdicts cover it too.
    $script:CleanupResults += [pscustomobject]@{
        Label = 'backend (restart step)'; Pid = $backendEntry.Process.Id
        Action = 'taskkill /T /F'; ExitCode = $restartKill.ExitCode; Confirmed = $restarted
    }
    $script:Started = @($script:Started | Where-Object { $_.Label -ne 'backend' })
    Add-Check -Name 'backend stopped cleanly on request' `
              -Pass ($restarted -and $restartKill.ExitCode -eq 0) `
              -Detail "taskkill exit $($restartKill.ExitCode), exited=$restarted"

    $backendLog2 = Join-Path $Evidence '12-backend-after-restart.log'
    [void](Start-Service -Label 'backend-restarted' -FilePath $python `
        -Arguments @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
        -WorkingDir $RepoRoot -LogFile $backendLog2)

    [void](Wait-ForHttp -Url "$Api/health" -TimeoutSec $ReadyTimeoutSec -Label 'backend after restart')
    Add-Check -Name 'backend is healthy again after restart' -Pass $true

    $runsPost = @(Invoke-Api -Path '/runs' -OutFile '43-runs-after-restart.json')
    $postRunIds = @($runsPost | ForEach-Object { $_.run_id } | Where-Object { $_ })
    $survived = @($runsPost | Where-Object { $_.run_id -eq $runId1 }).Count -eq 1
    Add-Check -Name 'run 1 survived the restart' -Pass $survived -Detail "history now holds $(@($runsPost).Count) run(s)"

    # The user's own history. Report each missing id by name; any loss fails.
    $missingOriginal = @()
    foreach ($id in $originalRunIds) {
        if (@($postRunIds | Where-Object { $_ -eq $id }).Count -eq 0) { $missingOriginal += $id }
    }
    $presLines = @("pre-existing runs : $(@($originalRunIds).Count)",
                   "still present     : $(@($originalRunIds).Count - @($missingOriginal).Count)",
                   "MISSING           : $(@($missingOriginal).Count)")
    foreach ($id in $missingOriginal) { $presLines += "  MISSING $id" }
    Write-Evidence -Name '43b-original-run-preservation.txt' -Text ($presLines -join "`r`n")
    foreach ($id in $missingOriginal) { Write-Warning "pre-existing run vanished: $id" }

    $preserveDetail = "$(@($originalRunIds).Count) pre-existing run(s) checked"
    if (@($missingOriginal).Count -gt 0) { $preserveDetail += "; missing: $($missingOriginal -join ', ')" }
    Add-Check -Name 'every pre-existing run is still present after restart' `
              -Pass (@($missingOriginal).Count -eq 0) -Detail $preserveDetail

    $run2 = Invoke-Api -Path '/run-sample' -Method POST -OutFile '44-run-2-after-restart.json'
    $runId2 = $run2.run_id
    Write-Host "  run 2: $runId2"

    $withPrev = @($run2.holdings | Where-Object { $null -ne $_.previous_run }).Count
    $totalHoldings = @($run2.holdings).Count
    Add-Check -Name 'hysteresis previous_run recovered from the store' `
              -Pass ($withPrev -eq $totalHoldings) -Detail "$withPrev of $totalHoldings holdings"

    $diff = Invoke-Api -Path "/runs/$runId2/diff" -OutFile '45-diff.json'
    Add-Check -Name 'diff links run 2 to run 1' -Pass ($diff.previous_run_id -eq $runId1) `
              -Detail "previous_run_id=$($diff.previous_run_id)"

    $policyPost = Invoke-Api -Path '/policy' -OutFile '46-policy-after-restart.json'
    $policySame = (($policyPre | ConvertTo-Json -Depth 12) -eq ($policyPost | ConvertTo-Json -Depth 12))
    Add-Check -Name 'policy is identical across the restart' -Pass $policySame

    # ------------------------------------------- 8. data preservation
    Write-Host ""
    Write-Host "[8/9] Existing user data preserved"

    $after = @(Snapshot-DataDir)
    $afterText = "files in data\ after: $($after.Count)"
    foreach ($item in $after) { $afterText += "`r`n  $($item.Relative)  $($item.Length) bytes  $($item.Hash)" }
    Write-Evidence -Name '51-data-after.txt' -Text $afterText

    $lost = @()
    $changed = @()
    $preserved = @()
    foreach ($item in $before) {
        $now = @($after | Where-Object { $_.Relative -eq $item.Relative })
        if ($now.Count -eq 0) { $lost += $item.Relative; continue }
        if ($now[0].Hash -ne $item.Hash) { $changed += $item.Relative; continue }
        $preserved += $item.Relative
    }

    $presText = @()
    $presText += "pre-existing files            : $($before.Count)"
    $presText += "still present, byte-identical : $($preserved.Count)"
    $presText += "still present, content changed: $($changed.Count)"
    $presText += "MISSING (destroyed)           : $($lost.Count)"
    if ($changed.Count) { $presText += "`r`nchanged:`r`n  $($changed -join "`r`n  ")" }
    if ($lost.Count)    { $presText += "`r`nMISSING:`r`n  $($lost -join "`r`n  ")" }
    $presText += "`r`nrun_ids before: $(@($runsPre).Count)  after: $(@($runsPost).Count)"
    Write-Evidence -Name '52-preservation.txt' -Text ($presText -join "`r`n")
    Write-Host ($presText -join "`r`n")

    Add-Check -Name 'no pre-existing file was destroyed' -Pass ($lost.Count -eq 0) -Detail "$($lost.Count) missing"

    # engine.db is append-only, so its hash legitimately changes. What must not
    # happen is a pre-existing run disappearing.
    $dbGrew = $true
    $dbNote = 'no pre-existing engine.db'
    $dbBefore = @($before | Where-Object { $_.Relative -eq 'engine.db' })
    if ($dbBefore.Count -eq 1) {
        $dbGrew = (@($runsPost).Count -ge @($runsPre).Count)
        $dbNote = "runs before=$(@($runsPre).Count) after=$(@($runsPost).Count)"
    }
    Add-Check -Name 'run store grew or held, never shrank (append-only)' -Pass $dbGrew -Detail $dbNote

    $policyUser = Join-Path $DataDir 'policy.yaml'
    $policyIntact = $true
    $policyNote = 'no user policy override present (nothing to preserve)'
    $policyEntry = @($before | Where-Object { $_.Relative -eq 'policy.yaml' })
    if ($policyEntry.Count -eq 1) {
        $policyNow = @($after | Where-Object { $_.Relative -eq 'policy.yaml' })
        $policyIntact = ($policyNow.Count -eq 1) -and ($policyNow[0].Hash -eq $policyEntry[0].Hash)
        $policyNote = "$policyUser unchanged"
    }
    Add-Check -Name 'user policy override untouched' -Pass $policyIntact -Detail $policyNote

    # ---------------------------------------------- 9. shipped launcher
    Write-Host ""
    Write-Host "[9/9] Shipped launcher (scripts\start.bat / stop.bat)"

    if (-not $IncludeLauncher) {
        Add-Check -Name 'launcher test skipped (pass -IncludeLauncher to run it)' -Pass $true
    }
    if ($IncludeLauncher) {
        Stop-StartedProcesses
        Start-Sleep -Seconds 2

        # Both ports must be free before start.bat runs. Any PID that then
        # appears on them was created by start.bat during THIS execution, which
        # is what makes it safe for us to own, verify and, if needed, terminate.
        $freeDeadline = (Get-Date).AddSeconds(20)
        $preOwnerB = Get-PortOwner -Port $BackendPort
        $preOwnerF = Get-PortOwner -Port $FrontendPort
        while ((Get-Date) -lt $freeDeadline) {
            if (-not $preOwnerB -and -not $preOwnerF) { break }
            Start-Sleep -Milliseconds 750
            $preOwnerB = Get-PortOwner -Port $BackendPort
            $preOwnerF = Get-PortOwner -Port $FrontendPort
        }
        if ($preOwnerB) { throw "port $BackendPort is still held by PID $preOwnerB after shutdown; launcher processes could not be attributed to this execution" }
        if ($preOwnerF) { throw "port $FrontendPort is still held by PID $preOwnerF after shutdown; launcher processes could not be attributed to this execution" }

        $launcherLog = Join-Path $Evidence '60-launcher-start.txt'
        $startBat = Join-Path $RepoRoot 'scripts\start.bat'
        & cmd.exe /c "`"$startBat`"" *> $launcherLog

        # Claim ownership as soon as the listeners appear, BEFORE waiting for
        # readiness. If start.bat never becomes healthy we still know which PIDs
        # it created, so the failure path can clean them up rather than orphaning
        # them.
        $launcherPids = @()
        $claimDeadline = (Get-Date).AddSeconds(60)
        while ((Get-Date) -lt $claimDeadline) {
            $launcherPids = @()
            $ownerB = Get-PortOwner -Port $BackendPort
            $ownerF = Get-PortOwner -Port $FrontendPort
            if ($ownerB) { $launcherPids += $ownerB }
            if ($ownerF) { $launcherPids += $ownerF }
            $launcherPids = @($launcherPids | Select-Object -Unique)
            if (@($launcherPids).Count -ge 2) { break }
            Start-Sleep -Milliseconds 750
        }

        # Register them as ours. If start.bat never becomes healthy and we
        # throw, the failure-path shutdown still terminates exactly these PIDs
        # instead of leaving them orphaned.
        foreach ($claimedPid in $launcherPids) {
            $claimed = Get-Process -Id $claimedPid -ErrorAction SilentlyContinue
            if ($claimed) {
                $script:Started += [pscustomobject]@{
                    Label = "launcher PID $claimedPid"; Process = $claimed
                }
            }
        }

        [void](Wait-ForHttp -Url "$Api/health" -TimeoutSec $ReadyTimeoutSec -Label 'start.bat backend')
        [void](Wait-ForHttp -Url $FrontendUrl  -TimeoutSec $ReadyTimeoutSec -Label 'start.bat interface')
        Add-Check -Name 'start.bat brings both services up' -Pass $true
        Write-Evidence -Name '60b-launcher-owned-pids.txt' `
                       -Text "launcher-owned PID(s): $($launcherPids -join ', ')"
        Write-Host "  launcher-owned PID(s): $($launcherPids -join ', ')"
        Add-Check -Name 'launcher-started processes identified and owned' `
                  -Pass (@($launcherPids).Count -ge 1) `
                  -Detail "$(@($launcherPids).Count) PID(s) on ports $BackendPort/$FrontendPort"

        $stopLog = Join-Path $Evidence '61-launcher-stop.txt'
        $stopBat = Join-Path $RepoRoot 'scripts\stop.bat'
        & cmd.exe /c "`"$stopBat`"" *> $stopLog
        # Poll until the owned PIDs are gone, not merely until the ports look
        # free - a lingering child would otherwise go unnoticed.
        $deadline2 = (Get-Date).AddSeconds(30)
        $survivors = @($launcherPids)
        while ((Get-Date) -lt $deadline2) {
            $survivors = @($launcherPids | Where-Object { Test-ProcessAlive -ProcessId $_ })
            if (@($survivors).Count -eq 0) { break }
            Start-Sleep -Milliseconds 750
        }
        $survivors = @($launcherPids | Where-Object { Test-ProcessAlive -ProcessId $_ })

        Add-Check -Name 'stop.bat terminated every launcher-started process' `
                  -Pass (@($survivors).Count -eq 0) `
                  -Detail "$(@($launcherPids).Count) owned, $(@($survivors).Count) still alive"

        $released = $true
        if (Get-PortOwner -Port $BackendPort)  { $released = $false }
        if (Get-PortOwner -Port $FrontendPort) { $released = $false }
        Add-Check -Name 'stop.bat releases both ports' -Pass $released

        # Anything stop.bat left behind is still ours, so clearing it stays
        # within "only what this execution started". Reported, not hidden.
        foreach ($leftPid in $survivors) {
            $kill = Invoke-Taskkill -ProcessId $leftPid
            $gone = $false
            $deadline3 = (Get-Date).AddSeconds(15)
            while ((Get-Date) -lt $deadline3) {
                if (-not (Test-ProcessAlive -ProcessId $leftPid)) { $gone = $true; break }
                Start-Sleep -Milliseconds 300
            }
            $script:CleanupResults += [pscustomobject]@{
                Label = 'launcher leftover (force-cleaned)'; Pid = $leftPid
                Action = 'taskkill /T /F'; ExitCode = $kill.ExitCode; Confirmed = $gone
            }
            Write-Warning "stop.bat left PID $leftPid running; terminated it (taskkill exit $($kill.ExitCode))"
        }
        if (@($survivors).Count -gt 0) {
            Add-Check -Name 'leftover launcher processes were force-cleaned' `
                      -Pass (@($script:CleanupResults | Where-Object { $_.Label -eq 'launcher leftover (force-cleaned)' -and -not $_.Confirmed }).Count -eq 0) `
                      -Detail "$(@($survivors).Count) leftover(s) terminated by this script"
        }
    }

    # --------------------------------------------------------------- done
    Write-Host ""
    Write-Host "Shutting down"
    Stop-StartedProcesses -Final

    $failedCount = @($script:Checks | Where-Object { $_.Result -eq 'FAIL' }).Count
    $outcome = 'ALL CHECKS PASSED'
    if ($failedCount -gt 0) { $outcome = "COMPLETED WITH $failedCount FAILED CHECK(S)" }

    Write-Summary -Outcome $outcome

    if ($failedCount -gt 0) { exit 1 }
    exit 0
}
catch {
    # Cleanup runs here and again on the success path above; there is no
    # separate cleanup block, so neither route can be skipped.
    $message = $_.Exception.Message
    Write-Host ""
    Write-Error -Message $message -ErrorAction Continue

    $errText = "FATAL: $message`r`n`r`n$($_.ScriptStackTrace)`r`n`r`n$($_.Exception.ToString())"
    Write-Evidence -Name '90-error.txt' -Text $errText

    Write-Host ""
    Write-Host "Shutting down after failure"
    Stop-StartedProcesses -Final

    Write-Summary -Outcome 'ABORTED' -FatalError $message
    exit 1
}
