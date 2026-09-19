# SPEC-0018 D07: listener ownership must be recorded independently of HTTP readiness.
# Execute only the AST-extracted function; never run the launcher or real OS commands.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$toriiSource = Join-Path $PSScriptRoot 'demo.ps1'
$toriiTokens = $null
$toriiErrors = $null
$toriiAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $toriiSource, [ref]$toriiTokens, [ref]$toriiErrors)
if ($toriiErrors.Count) { throw 'Launcher has PowerShell parse errors.' }
$toriiFunction = $toriiAst.Find({
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Record-DemoListener'
}, $true)
if (-not $toriiFunction) { throw 'RED: Record-DemoListener is missing.' }

# These shadows are deliberately script-local and capture all effects in memory.
$script:toriiTestListeners = @()
$script:toriiTestServer = $null
$script:toriiTestWrites = [System.Collections.Generic.List[object]]::new()
$script:toriiTestHttpCalls = 0
function Get-NetTCPConnection {
    [CmdletBinding()]
    param($State, $LocalAddress, $LocalPort)
    if ($State -ne 'Listen' -or $LocalAddress -ne '127.0.0.1' -or $LocalPort -ne 18440) {
        throw 'The query must target the exact demo listener.'
    }
    $script:toriiTestListeners
}
function Get-CimInstance {
    [CmdletBinding()]
    param([Parameter(Position = 0)]$ClassName, $Filter)
    if ($ClassName -ne 'Win32_Process' -or $Filter -ne "ProcessId=$($script:toriiTestServer.ProcessId)") {
        throw 'The process query must match the observed listener PID.'
    }
    $script:toriiTestServer
}
function Set-Content {
    [CmdletBinding()]
    param($LiteralPath, [Parameter(ValueFromPipeline = $true)]$Value)
    process { $script:toriiTestWrites.Add([pscustomobject]@{ Path = $LiteralPath; Value = $Value }) }
}
function Get-DemoState { $script:toriiTestHttpCalls++; throw 'HTTP readiness must not be queried.' }
function Invoke-RestMethod { throw 'No HTTP is permitted in this test.' }
function Start-Process { throw 'No process launch is permitted in this test.' }
function Stop-Process { throw 'No process termination is permitted in this test.' }

. ([scriptblock]::Create($toriiFunction.Extent.Text))
$toriiProc = [pscustomobject]@{ Id = 101 }
$toriiData = 'C:\synthetic-torii\apps\demo\.local\data'
$toriiPidFile = 'C:\synthetic-torii\apps\demo\.local\process.json'
$toriiCreated = [datetime]'2026-09-19T10:20:30.1234567Z'

function Assert-Case($condition, [string]$message) {
    if (-not $condition) { throw $message }
}
function Set-TestListener([int]$processId, [int]$parentId) {
    $script:toriiTestListeners = @([pscustomobject]@{ OwningProcess = $processId })
    $script:toriiTestServer = [pscustomobject]@{
        ProcessId = $processId
        ParentProcessId = $parentId
        ExecutablePath = 'C:\synthetic-python\python.exe'
        CommandLine = "python.exe -m torii_demo --local-demo --data-dir `"$toriiData`""
        CreationDate = $toriiCreated
    }
    $script:toriiTestWrites.Clear()
}
function Assert-Recorded([int]$expectedPid) {
    Assert-Case ($script:toriiTestWrites.Count -eq 1) 'Expected exactly one in-memory record write.'
    Assert-Case ($script:toriiTestWrites[0].Path -eq $toriiPidFile) 'Record used an unexpected path.'
    $record = $script:toriiTestWrites[0].Value | ConvertFrom-Json
    Assert-Case ($record.pid -eq $expectedPid) 'Recorded PID differs from verified listener.'
    Assert-Case ($record.executable -eq $script:toriiTestServer.ExecutablePath) 'Executable not preserved.'
    Assert-Case (([datetime]$record.created).ToUniversalTime().Ticks -eq $toriiCreated.ToUniversalTime().Ticks) 'Creation instant not preserved.'
    Assert-Case ($script:toriiTestHttpCalls -eq 0) 'Ownership was coupled to HTTP readiness.'
}

Assert-Case ((Record-DemoListener) -eq $false) 'An absent listener must return false.'
Assert-Case ($script:toriiTestWrites.Count -eq 0) 'An absent listener must not write a record.'

Set-TestListener 202 101
Assert-Case ((Record-DemoListener) -eq $true) 'A verified direct child must be accepted.'
Assert-Recorded 202

Set-TestListener 303 999
$toriiRefused = $false
try { Record-DemoListener | Out-Null } catch { $toriiRefused = $true }
Assert-Case $toriiRefused 'A foreign process must be refused.'
Assert-Case ($script:toriiTestWrites.Count -eq 0) 'A foreign process must not replace the record.'

Set-TestListener 101 999
Assert-Case ((Record-DemoListener) -eq $true) 'The directly launched listener must be accepted.'
Assert-Recorded 101

Write-Host 'PASS: 4 demo launcher ownership cases; no real HTTP, processes, or file writes.'
