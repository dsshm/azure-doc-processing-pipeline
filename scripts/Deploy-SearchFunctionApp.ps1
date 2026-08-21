<#
.SYNOPSIS
Packages and deploys the SearchDocuments Azure Function facade.

.DESCRIPTION
Creates a zip package from the functionapp folder and deploys it to the Azure
Function App resource created by Bicep or Terraform. By default, returns a
host-key-protected SearchDocuments URL for Power Apps.

.EXAMPLE
.\scripts\Deploy-SearchFunctionApp.ps1 -ResourceGroupName rg-docpipeline-maps-test -FunctionAppName func-docpipeline-test-jd7zqs
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$FunctionAppName,

    [Parameter()]
    [string]$SubscriptionId = "",

    [Parameter()]
    [string]$ProjectPath = (Join-Path $PSScriptRoot "..\functionapp"),

    [Parameter()]
    [string]$PackagePath = "",

    [Parameter()]
    [switch]$SkipFunctionUrl
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

function Invoke-AzCli {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & az @Arguments 2>&1
    $output = @($output | Where-Object {
        $_ -notmatch "UserWarning: You are using cryptography on a 32-bit Python" -and
        $_ -notmatch "Cryptography will be significantly faster if you switch to using a 64-bit Python"
    })
    if ($LASTEXITCODE -ne 0) {
        throw "az $($Arguments -join ' ') failed:`n$($output -join [Environment]::NewLine)"
    }

    return $output
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required."
}

if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
    throw "Function App project path '$ProjectPath' does not exist."
}

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    Invoke-AzCli -Arguments @("account", "set", "--subscription", $SubscriptionId) | Out-Null
}
else {
    $SubscriptionId = ((Invoke-AzCli -Arguments @("account", "show", "--query", "id", "-o", "tsv")) -join "").Trim()
}

$temporaryPackage = [string]::IsNullOrWhiteSpace($PackagePath)
$temporaryStaging = Join-Path ([System.IO.Path]::GetTempPath()) ("functionapp-$FunctionAppName-{0}" -f ([Guid]::NewGuid().ToString("N")))
if ($temporaryPackage) {
    $PackagePath = Join-Path ([System.IO.Path]::GetTempPath()) ("functionapp-$FunctionAppName-{0}.zip" -f ([Guid]::NewGuid().ToString("N")))
}

try {
    if (Test-Path -LiteralPath $PackagePath) {
        Remove-Item -LiteralPath $PackagePath -Force
    }

    New-Item -ItemType Directory -Path $temporaryStaging | Out-Null

    $excludedNames = @(
        ".venv",
        "__pycache__",
        ".python_packages",
        "local.settings.json"
    )

    Get-ChildItem -LiteralPath $ProjectPath -Force | Where-Object {
        $excludedNames -notcontains $_.Name
    } | Copy-Item -Destination $temporaryStaging -Recurse -Force

    Compress-Archive -Path (Join-Path $temporaryStaging "*") -DestinationPath $PackagePath -Force

    Invoke-AzCli -Arguments @(
        "functionapp", "deployment", "source", "config-zip",
        "--resource-group", $ResourceGroupName,
        "--name", $FunctionAppName,
        "--src", $PackagePath,
        "--build-remote", "true"
    ) | Out-Null

    $functionUrl = ""
    if (-not $SkipFunctionUrl) {
        $hostName = ((Invoke-AzCli -Arguments @(
            "functionapp", "show",
            "--resource-group", $ResourceGroupName,
            "--name", $FunctionAppName,
            "--query", "defaultHostName",
            "-o", "tsv"
        )) -join "").Trim()

        $functionKey = ((Invoke-AzCli -Arguments @(
            "functionapp", "keys", "list",
            "--resource-group", $ResourceGroupName,
            "--name", $FunctionAppName,
            "--query", "functionKeys.default",
            "-o", "tsv"
        )) -join "").Trim()

        $functionUrl = "https://$hostName/api/SearchDocuments?code=$functionKey"
    }

    [pscustomobject]@{
        FunctionAppName = $FunctionAppName
        ResourceGroupName = $ResourceGroupName
        PackagePath = $PackagePath
        FunctionUrl = $functionUrl
    }
}
finally {
    if (Test-Path -LiteralPath $temporaryStaging) {
        Remove-Item -LiteralPath $temporaryStaging -Recurse -Force
    }
    if ($temporaryPackage -and (Test-Path -LiteralPath $PackagePath)) {
        Remove-Item -LiteralPath $PackagePath -Force
    }
}
