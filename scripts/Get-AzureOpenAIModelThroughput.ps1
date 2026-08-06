<#
.SYNOPSIS
Reports Azure OpenAI deployment capacity and regional usage/quota with Azure CLI.

.DESCRIPTION
Uses az CLI/ARM calls to show the configured capacity for Azure OpenAI model
deployments and the available regional Cognitive Services usage/quota records.
This is useful when the Azure portal redirects OpenAI account management to
Foundry and you need CLI-visible throughput evidence.

For Standard/GlobalStandard Azure OpenAI deployments, deployment SKU capacity is
commonly expressed in thousands of tokens per minute (TPM). Provisioned SKUs use
different units, so the script prints the raw capacity units as well as a TPM
estimate only for non-provisioned deployment SKUs.

.EXAMPLE
.\scripts\Get-AzureOpenAIModelThroughput.ps1 `
  -SubscriptionId 00000000-0000-0000-0000-000000000000 `
  -ResourceGroupName rg-docpipeline-prod `
  -AccountName oai-docpipeline-prod-abc123

.EXAMPLE
.\scripts\Get-AzureOpenAIModelThroughput.ps1 -SubscriptionId 00000000-0000-0000-0000-000000000000
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$SubscriptionId = "",

    [Parameter()]
    [string]$ResourceGroupName = "",

    [Parameter()]
    [string]$AccountName = "",

    [Parameter()]
    [string]$Location = "",

    [Parameter()]
    [switch]$RawJson
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

function Invoke-AzCliJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $output = Invoke-AzCli -Arguments $Arguments
    $json = ($output -join [Environment]::NewLine).Trim()
    if ([string]::IsNullOrWhiteSpace($json)) {
        return $null
    }

    return $json | ConvertFrom-Json
}

function Get-ResourceGroupFromId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ResourceId
    )

    if ($ResourceId -notmatch "/resourceGroups/([^/]+)/") {
        throw "Could not parse resource group from resource ID '$ResourceId'."
    }

    return $Matches[1]
}

function Get-AoaiAccounts {
    $resources = @(Invoke-AzCliJson -Arguments @(
        "resource", "list",
        "--subscription", $SubscriptionId,
        "--resource-type", "Microsoft.CognitiveServices/accounts"
    ))

    $accounts = foreach ($resource in $resources) {
        if (-not [string]::IsNullOrWhiteSpace($ResourceGroupName) -and $resource.resourceGroup -ne $ResourceGroupName) {
            continue
        }
        if (-not [string]::IsNullOrWhiteSpace($AccountName) -and $resource.name -ne $AccountName) {
            continue
        }
        if ($resource.kind -ne "OpenAI") {
            continue
        }

        $rg = if ($resource.resourceGroup) { $resource.resourceGroup } else { Get-ResourceGroupFromId -ResourceId $resource.id }
        Invoke-AzCliJson -Arguments @(
            "cognitiveservices", "account", "show",
            "--subscription", $SubscriptionId,
            "--resource-group", $rg,
            "--name", $resource.name
        )
    }

    return @($accounts)
}

function Get-AoaiDeployments {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Account
    )

    $url = "https://management.azure.com$($Account.id)/deployments?api-version=2024-10-01"
    $response = Invoke-AzCliJson -Arguments @("rest", "--method", "get", "--url", $url)
    return @($response.value)
}

function Get-CognitiveUsage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$UsageLocation
    )

    $url = "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.CognitiveServices/locations/$UsageLocation/usages?api-version=2023-05-01"
    try {
        $response = Invoke-AzCliJson -Arguments @("rest", "--method", "get", "--url", $url)
        return @($response.value)
    }
    catch {
        Write-Warning "Could not read Cognitive Services usage for location '$UsageLocation': $($_.Exception.Message)"
        return @()
    }
}

function Get-UsageName {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Usage
    )

    $localizedValue = $Usage.name.PSObject.Properties["localizedValue"]
    if ($localizedValue -and -not [string]::IsNullOrWhiteSpace([string]$localizedValue.Value)) {
        return [string]$localizedValue.Value
    }

    $value = $Usage.name.PSObject.Properties["value"]
    if ($value) {
        return [string]$value.Value
    }

    return ""
}

function Test-OpenAIUsageRecord {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Usage
    )

    $value = $Usage.name.PSObject.Properties["value"]
    $name = "$(Get-UsageName -Usage $Usage) $(if ($value) { $value.Value } else { '' })"
    return $name -match "OpenAI|GPT|gpt|embedding|Embedding|Tokens|TPM|PTU|GlobalStandard|Standard"
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required."
}

if ([string]::IsNullOrWhiteSpace($SubscriptionId)) {
    $SubscriptionId = ((Invoke-AzCli -Arguments @("account", "show", "--query", "id", "-o", "tsv")) -join "").Trim()
}

Invoke-AzCli -Arguments @("account", "set", "--subscription", $SubscriptionId) | Out-Null

$accounts = Get-AoaiAccounts
if ($accounts.Count -eq 0) {
    throw "No Azure OpenAI Cognitive Services accounts matched the provided filters."
}

$locations = @(
    $accounts |
        ForEach-Object { if ([string]::IsNullOrWhiteSpace($Location)) { $_.location } else { $Location } } |
        Select-Object -Unique
)

$usageRows = foreach ($usageLocation in $locations) {
    foreach ($usage in Get-CognitiveUsage -UsageLocation $usageLocation) {
        if (Test-OpenAIUsageRecord -Usage $usage) {
            $nameValue = $usage.name.PSObject.Properties["value"]
            [pscustomobject]@{
                Location = $usageLocation
                Name = Get-UsageName -Usage $usage
                NameValue = if ($nameValue) { [string]$nameValue.Value } else { "" }
                CurrentValue = $usage.currentValue
                Limit = $usage.limit
                Unit = $usage.unit
            }
        }
    }
}

$deploymentRows = foreach ($account in $accounts) {
    $deployments = Get-AoaiDeployments -Account $account
    foreach ($deployment in $deployments) {
        $skuName = [string]$deployment.sku.name
        $capacity = $deployment.sku.capacity
        $isProvisioned = $skuName -match "Provisioned|PTU"
        $estimatedTpm = if ($null -ne $capacity -and -not $isProvisioned) { [int]$capacity * 1000 } else { $null }

        [pscustomobject]@{
            AccountName = $account.name
            ResourceGroupName = Get-ResourceGroupFromId -ResourceId $account.id
            Location = $account.location
            DeploymentName = $deployment.name
            ModelName = $deployment.properties.model.name
            ModelVersion = $deployment.properties.model.version
            SkuName = $skuName
            CapacityUnits = $capacity
            EstimatedAllocatedTPM = $estimatedTpm
            ProvisioningState = $deployment.properties.provisioningState
        }
    }
}

$result = [pscustomobject]@{
    SubscriptionId = $SubscriptionId
    AccountsScanned = $accounts.Count
    Deployments = @($deploymentRows)
    RegionalUsage = @($usageRows)
    Notes = @(
        "Deployment CapacityUnits is the configured deployment capacity from ARM.",
        "For Standard/GlobalStandard deployments, EstimatedAllocatedTPM is CapacityUnits * 1000.",
        "RegionalUsage rows are subscription/location quota and current usage records exposed by Microsoft.CognitiveServices."
    )
}

if ($RawJson) {
    $result | ConvertTo-Json -Depth 10
    return
}

Write-Host "Azure OpenAI deployment capacity" -ForegroundColor Cyan
$deploymentRows | Sort-Object AccountName, DeploymentName | Format-Table -AutoSize

Write-Host ""
Write-Host "Regional Cognitive Services / OpenAI quota and usage" -ForegroundColor Cyan
if (@($usageRows).Count -eq 0) {
    Write-Warning "No OpenAI-looking usage rows were returned. Re-run with -RawJson if you want the full structured output."
}
else {
    $usageRows | Sort-Object Location, Name | Format-Table -AutoSize
}

Write-Host ""
Write-Host "Notes" -ForegroundColor Cyan
$result.Notes | ForEach-Object { Write-Host "- $_" }
