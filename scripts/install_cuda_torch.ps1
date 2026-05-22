param(
    [string]$PythonPath = "",
    [ValidateSet("cu124", "cu126", "cu128")]
    [string]$CudaWheel = "cu124",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Resolve-PythonPath {
    param([string]$RepoRoot, [string]$ProvidedPythonPath)

    if (-not [string]::IsNullOrWhiteSpace($ProvidedPythonPath)) {
        return $ProvidedPythonPath
    }

    foreach ($candidate in @("conda/python.exe", "conda/Scripts/python.exe", ".conda/python.exe", ".conda/Scripts/python.exe")) {
        $path = Join-Path $RepoRoot $candidate
        if (Test-Path -LiteralPath $path) {
            return $path
        }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return $pythonCommand.Source
    }

    throw "Python interpreter not found. Pass -PythonPath or create the repo conda environment first."
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Resolve-PythonPath -RepoRoot $repoRoot -ProvidedPythonPath $PythonPath
$indexUrl = "https://download.pytorch.org/whl/$CudaWheel"
$installArgs = @(
    "-m",
    "pip",
    "install",
    "--upgrade",
    "--force-reinstall",
    "torch",
    "torchvision",
    "torchaudio",
    "--index-url",
    $indexUrl
)

Write-Output "Python: $python"
Write-Output "PyTorch CUDA wheel index: $indexUrl"
Write-Output "Command: `"$python`" $($installArgs -join ' ')"

if ($DryRun) {
    exit 0
}

& $python @installArgs
if ($LASTEXITCODE -ne 0) {
    throw "CUDA PyTorch installation failed."
}

& $python -c "import torch; print('torch_version=' + torch.__version__); print('cuda_available=' + str(torch.cuda.is_available())); print('cuda_version=' + str(torch.version.cuda)); print('device_count=' + str(torch.cuda.device_count())); print('device_name=' + (torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''))"
if ($LASTEXITCODE -ne 0) {
    throw "CUDA PyTorch verification failed."
}
