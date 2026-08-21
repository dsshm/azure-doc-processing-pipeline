<#
.SYNOPSIS
Packages and deploys the Logic App Standard workflow project.

.DESCRIPTION
Creates a zip package from the logicapp folder and deploys it to the Logic App
Standard resource created by the Bicep deployment. The script can also return
the key-protected HTTP trigger callback URL for the SearchDocuments workflow.

.EXAMPLE
.\scripts\Deploy-LogicAppWorkflow.ps1 -ResourceGroupName rg-docpipeline-maps-test -LogicAppName logic-docpipeline-test-jd7zqs
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory = $true)]
    [string]$LogicAppName,

    [Parameter()]
    [string]$SubscriptionId = "",

    [Parameter()]
    [string]$ProjectPath = (Join-Path $PSScriptRoot "..\logicapp"),

    [Parameter()]
    [string]$PackagePath = "",

    [Parameter()]
    [switch]$SkipCallbackUrl
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

function Invoke-AzCli {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = & az @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "az $($Arguments -join ' ') failed:`n$($output -join [Environment]::NewLine)"
    }

    return $output
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required."
}

if (-not (Test-Path -LiteralPath $ProjectPath -PathType Container)) {
    throw "Logic App project path '$ProjectPath' does not exist."
}

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    Invoke-AzCli -Arguments @("account", "set", "--subscription", $SubscriptionId) | Out-Null
}
else {
    $SubscriptionId = ((Invoke-AzCli -Arguments @("account", "show", "--query", "id", "-o", "tsv")) -join "").Trim()
}

$temporaryPackage = [string]::IsNullOrWhiteSpace($PackagePath)
if ($temporaryPackage) {
    $PackagePath = Join-Path ([System.IO.Path]::GetTempPath()) ("logicapp-$LogicAppName-{0}.zip" -f ([Guid]::NewGuid().ToString("N")))
}

try {
    if (Test-Path -LiteralPath $PackagePath) {
        Remove-Item -LiteralPath $PackagePath -Force
    }

    Compress-Archive -Path (Join-Path $ProjectPath "*") -DestinationPath $PackagePath -Force

    Invoke-AzCli -Arguments @(
        "webapp", "deployment", "source", "config-zip",
        "--resource-group", $ResourceGroupName,
        "--name", $LogicAppName,
        "--src", $PackagePath
    ) | Out-Null

    $callbackUrl = ""
    if (-not $SkipCallbackUrl) {
        $callbackUrl = ((Invoke-AzCli -Arguments @(
            "rest",
            "--method", "post",
            "--uri", "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroupName/providers/Microsoft.Web/sites/$LogicAppName/hostruntime/runtime/webhooks/workflow/api/management/workflows/SearchDocuments/triggers/manual/listCallbackUrl?api-version=2024-04-01",
            "--query", "value",
            "-o", "tsv"
        )) -join "").Trim()
    }

    [pscustomobject]@{
        LogicAppName = $LogicAppName
        ResourceGroupName = $ResourceGroupName
        PackagePath = $PackagePath
        TriggerUrl = $callbackUrl
    }
}
finally {
    if ($temporaryPackage -and (Test-Path -LiteralPath $PackagePath)) {
        Remove-Item -LiteralPath $PackagePath -Force
    }
}
