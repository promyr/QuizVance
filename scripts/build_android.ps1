param(
    [ValidateSet("apk", "aab", "both")]
    [string]$Target = "both",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:RICH_NO_COLOR = "1"

# Tenta corrigir PATH se necessario
if (-not (Get-Command flet -ErrorAction SilentlyContinue)) {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $pyPath = (Get-Command python).Source
        $scriptsDir = Join-Path (Split-Path -Parent $pyPath) "Scripts"
        if (Test-Path $scriptsDir) {
            Write-Host "Adicionando Scripts ao PATH: $scriptsDir"
            $env:Path = "$scriptsDir;$env:Path"
        }
    }
}

# Configura executavel do flet
$FletExe = "flet"
if (-not (Get-Command flet -ErrorAction SilentlyContinue)) {
    # Tenta caminho conhecido
    $KnownPath = "C:\Users\Belchior\AppData\Local\Python\pythoncore-3.14-64\Scripts\flet.exe"
    if (Test-Path $KnownPath) {
        Write-Host "Usando flet em: $KnownPath"
        $FletExe = $KnownPath
    }
    else {
        # Tenta dinamico via python se disponivel
        if (Get-Command python -ErrorAction SilentlyContinue) {
            $pyPath = (Get-Command python).Source
            $scriptsDir = Join-Path (Split-Path -Parent $pyPath) "Scripts"
            $dynPath = Join-Path $scriptsDir "flet.exe"
            if (Test-Path $dynPath) {
                Write-Host "Usando flet via python: $dynPath"
                $FletExe = $dynPath
            }
        }
    }
}

# Verificacao final
if (-not (Get-Command $FletExe -ErrorAction SilentlyContinue) -and -not (Test-Path $FletExe)) {
    throw "Flet nao encontrado. Verifique se esta instalado."
}

# Assert-Command removido pois ja verificamos o flet acima.
# Assert-Command "flet"

function Invoke-FletBuild($platform, $args, $rootDir) {
    # Usa escopo de script para acessar a variavel correta se necessario, mas aqui esta no mesmo escopo de arquivo
    Write-Host "==> $script:FletExe build $platform"
    & $script:FletExe build @args $platform "."
    if ($LASTEXITCODE -eq 0) {
        return
    }

    # Workaround Windows
    $artifact = if ($platform -eq "apk") {
        Join-Path $rootDir "build\flutter\build\app\outputs\flutter-apk\app-release.apk"
    }
    else {
        Join-Path $rootDir "build\flutter\build\app\outputs\bundle\release\app-release.aab"
    }

    if (Test-Path $artifact) {
        Write-Warning "Build retornou codigo de erro, mas artefato existe: $artifact"
        return
    }

    throw "Falha no build $platform"
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $rootDir

$commonArgs = @(
    "--project", "quiz-vance",
    "--product", "Quiz Vance",
    "--org", "br.quizvance",
    "--bundle-id", "br.quizvance.app",
    "--build-version", "2.0.0",
    "--build-number", "1",
    "--no-rich-output",
    "--clear-cache",
    "--yes"
)

if ($OutputDir) {
    $commonArgs += @("--output", $OutputDir)
}

# Assinatura opcional para release na Play Store.
$keystore = $env:ANDROID_SIGNING_KEY_STORE
$storePwd = $env:ANDROID_SIGNING_KEY_STORE_PASSWORD
$keyPwd = $env:ANDROID_SIGNING_KEY_PASSWORD
$keyAlias = $env:ANDROID_SIGNING_KEY_ALIAS
if ($keystore -and $storePwd -and $keyPwd) {
    $commonArgs += @("--android-signing-key-store", $keystore)
    $commonArgs += @("--android-signing-key-store-password", $storePwd)
    $commonArgs += @("--android-signing-key-password", $keyPwd)
    if ($keyAlias) {
        $commonArgs += @("--android-signing-key-alias", $keyAlias)
    }
    Write-Host "==> Assinatura Android habilitada."
}
else {
    Write-Host "==> Assinatura Android nao configurada. Sera gerado build de debug/local."
}

if ($Target -in @("apk", "both")) {
    Invoke-FletBuild "apk" $commonArgs $rootDir
}

if ($Target -in @("aab", "both")) {
    Invoke-FletBuild "aab" $commonArgs $rootDir
}

Write-Host "Build Android concluido."
