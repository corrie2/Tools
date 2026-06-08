param(
    [string]$Workspace = (Get-Location).Path,
    [string]$DatabaseUrl = "",
    [string]$MemoryPython = "",
    [switch]$SkipInitDb,
    [string]$AgentExecutable = "",
    [string]$AgentArgsJson = "[]",
    [string]$AgentArgsBase64 = ""
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$memorySession = Join-Path $repoRoot "skills\agent-long-memory\scripts\memory_session.py"
$resolvedWorkspace = (Resolve-Path -LiteralPath $Workspace).Path

if (-not $MemoryPython) {
    $repoParent = Split-Path -Parent $repoRoot
    $toolsPython = Join-Path $repoParent ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $toolsPython) {
        $MemoryPython = $toolsPython
    } else {
        $MemoryPython = "python"
    }
}

if (-not $DatabaseUrl) {
    if ($env:PPT_AGENT_MEMORY_DATABASE_URL) {
        $DatabaseUrl = $env:PPT_AGENT_MEMORY_DATABASE_URL
    } else {
        $DatabaseUrl = "postgresql://ppt_agent:ppt_agent@127.0.0.1:54329/ppt_agent_memory"
    }
}

$env:PPT_AGENT_VECTOR_MEMORY = "1"
$env:PPT_AGENT_MEMORY_DATABASE_URL = $DatabaseUrl
$env:PPT_AGENT_MEMORY_PROJECT_ROOT = $resolvedWorkspace
$env:PPT_AGENT_MEMORY_SCOPE_MODE = "workspace"

if (-not $SkipInitDb) {
    & $MemoryPython $memorySession init-db | Write-Output
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

& $MemoryPython $memorySession status --workspace $resolvedWorkspace | Write-Output
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($AgentExecutable) {
    if ($AgentArgsBase64) {
        $AgentArgsJson = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($AgentArgsBase64))
    }
    $agentArgs = ConvertFrom-Json -InputObject $AgentArgsJson
    if ($null -eq $agentArgs) {
        $agentArgs = @()
    }
    & $AgentExecutable @agentArgs
    exit $LASTEXITCODE
}
