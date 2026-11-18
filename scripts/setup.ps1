[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root

function New-HexSecret([int]$bytes) {
    $buffer = New-Object byte[] $bytes
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    try {
        $rng.GetBytes($buffer)
    } finally {
        $rng.Dispose()
    }
    return ([BitConverter]::ToString($buffer)).Replace('-', '').ToLowerInvariant()
}

function Invoke-DockerCompose([string[]]$Arguments) {
    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose falhou (código $LASTEXITCODE)."
    }
}

if (-not (Test-Path -LiteralPath '.env')) {
    $databasePassword = New-HexSecret 32
    $jwtSecret = New-HexSecret 48
    $environmentContent = @(
        "POSTGRES_PASSWORD=$databasePassword"
        "JWT_SECRET_KEY=$jwtSecret"
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText((Join-Path $root '.env'), $environmentContent, (New-Object Text.UTF8Encoding($false)))
}

if (-not (Test-Path -LiteralPath '.admin-credentials')) {
    $adminPassword = "Jz!$(New-HexSecret 24)"
    [IO.File]::WriteAllText((Join-Path $root '.admin-credentials'), $adminPassword, (New-Object Text.UTF8Encoding($false)))
}

Invoke-DockerCompose @('build')
Invoke-DockerCompose @('--profile', 'setup', 'run', '--rm', 'migrate')
Invoke-DockerCompose @('--profile', 'setup', 'run', '--rm', 'seed')
Invoke-DockerCompose @('up', '-d', '--wait', 'app')
Write-Output 'Prévia iniciada em http://127.0.0.1:8330. A senha do administrador está em .admin-credentials.'
