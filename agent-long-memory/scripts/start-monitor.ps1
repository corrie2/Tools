param(
    [string]$DatabaseUrl = "postgresql://codex_memory:codex@127.0.0.1:54329/codex_memory",
    [string]$ProjectsFile = "",
    [string]$AllowedWorkspaces = "",
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8081,
    [switch]$UsePool
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptRoot
$repoParent = Split-Path -Parent $repoRoot
$python = Join-Path $repoParent ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    $python = "python"
}

if (-not $ProjectsFile) {
    if ($env:CODEX_HOME) {
        $ProjectsFile = Join-Path $env:CODEX_HOME "agent-long-memory-projects.json"
    } else {
        $ProjectsFile = Join-Path $HOME ".codex\agent-long-memory-projects.json"
    }
}

$env:PPT_AGENT_VECTOR_MEMORY = "1"
$env:PPT_AGENT_MEMORY_DATABASE_URL = $DatabaseUrl
$env:PPT_AGENT_MEMORY_USE_POOL = if ($UsePool) { "1" } else { "0" }
$env:PPT_AGENT_MEMORY_PROJECTS_FILE = $ProjectsFile
if ($AllowedWorkspaces) {
    $env:PPT_AGENT_MEMORY_ALLOWED_WORKSPACES = $AllowedWorkspaces
}

Write-Output "Starting Agent Long Memory monitor..."
Write-Output "URL: http://$HostAddress`:$Port"
Write-Output "Projects file: $ProjectsFile"
if ($AllowedWorkspaces) {
    Write-Output "Additional allowed workspaces from environment: $AllowedWorkspaces"
}

& $python (Join-Path $repoRoot "run_monitor.py") --host $HostAddress --port $Port
exit $LASTEXITCODE
