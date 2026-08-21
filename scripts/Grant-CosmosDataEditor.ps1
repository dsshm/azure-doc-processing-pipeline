<# 
.SYNOPSIS
Grants one or more Microsoft Entra users editor access to a Cosmos DB for NoSQL account.

.DESCRIPTION
Assigns the Cosmos DB Built-in Data Contributor SQL data-plane role so users can create,
read, update, query, and delete Cosmos DB items using Microsoft Entra authentication.
By default, it also assigns the Azure RBAC Cosmos DB Operator role at the account scope so
users can manage databases and containers without granting account keys.

Requires the caller to have permissions to create both Cosmos SQL data-plane role
assignments and Azure RBAC role assignments, such as Owner or User Access Administrator
plus Cosmos DB account role-assignment permissions.

.EXAMPLE
.\scripts\Grant-CosmosDataEditor.ps1 -User user1@contoso.com,user2@contoso.com

.EXAMPLE
.\scripts\Grant-CosmosDataEditor.ps1 -User 00000000-0000-0000-0000-000000000000 -SkipCosmosOperatorRole
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter()]
    [string]$SubscriptionId = "9698dd71-9367-49c2-bede-fd0deecfad62",

    [Parameter()]
    [string]$ResourceGroupName = "rg-docpipeline-maps-test",

    [Parameter()]
    [string]$AccountName = "cosmos-docpipeline-test-jd7zqs",

    [Parameter(Mandatory = $true)]
    [Alias("Users")]
    [string[]]$User,

    [Parameter()]
    [ValidateSet("User", "Group", "ServicePrincipal")]
    [string]$PrincipalType = "User",

    [Parameter()]
    [string]$DataPlaneScope = "",

    [Parameter()]
    [switch]$SkipCosmosOperatorRole
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

$cosmosDataContributorRoleDefinitionGuid = "00000000-0000-0000-0000-000000000002"
$cosmosOperatorRoleName = "Cosmos DB Operator"

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

function Resolve-PrincipalId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Identity
    )

    $candidate = $Identity.Trim()
    $parsedGuid = [Guid]::Empty
    if ([Guid]::TryParse($candidate, [ref]$parsedGuid)) {
        return $parsedGuid.Guid
    }

    if ($PrincipalType -ne "User") {
        throw "Principal '$candidate' is not a GUID. For PrincipalType '$PrincipalType', pass the object ID."
    }

    try {
        $objectId = Invoke-AzCli -Arguments @("ad", "user", "show", "--id", $candidate, "--query", "id", "-o", "tsv")
        return (($objectId -join "")).Trim()
    }
    catch {
        throw "Could not resolve '$candidate' to a user object ID. Pass the object ID directly or run with an identity that can read users from Microsoft Graph. $($_.Exception.Message)"
    }
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required."
}

Invoke-AzCli -Arguments @("account", "set", "--subscription", $SubscriptionId) | Out-Null

$cosmosAccountId = (Invoke-AzCli -Arguments @(
    "cosmosdb", "show",
    "--subscription", $SubscriptionId,
    "--resource-group", $ResourceGroupName,
    "--name", $AccountName,
    "--query", "id",
    "-o", "tsv"
) | Select-Object -First 1).Trim()

$effectiveDataPlaneScope = if ([string]::IsNullOrWhiteSpace($DataPlaneScope)) { $cosmosAccountId } else { $DataPlaneScope }
$dataContributorRoleDefinitionId = "$cosmosAccountId/sqlRoleDefinitions/$cosmosDataContributorRoleDefinitionGuid"

$cosmosOperatorRoleDefinitionId = $null
if (-not $SkipCosmosOperatorRole) {
    $roleDefinitionIds = @(Invoke-AzCli -Arguments @(
        "role", "definition", "list",
        "--name", $cosmosOperatorRoleName,
        "--query", "[].id",
        "-o", "tsv"
    ))
    if ($roleDefinitionIds.Count -eq 0) {
        throw "Could not find Azure RBAC role definition '$cosmosOperatorRoleName'."
    }
    $cosmosOperatorRoleDefinitionId = ($roleDefinitionIds | Select-Object -First 1).Trim()
}

$results = foreach ($identity in $User) {
    $principalId = Resolve-PrincipalId -Identity $identity

    $sqlAssignments = @(Invoke-AzCliJson -Arguments @(
        "cosmosdb", "sql", "role", "assignment", "list",
        "--subscription", $SubscriptionId,
        "--resource-group", $ResourceGroupName,
        "--account-name", $AccountName
    ))

    $existingSqlAssignment = $sqlAssignments | Where-Object {
        $_.principalId -eq $principalId -and
        $_.roleDefinitionId -eq $dataContributorRoleDefinitionId -and
        $_.scope -eq $effectiveDataPlaneScope
    } | Select-Object -First 1

    $dataContributorStatus = "AlreadyExists"
    if (-not $existingSqlAssignment) {
        if ($PSCmdlet.ShouldProcess($principalId, "Assign Cosmos DB Built-in Data Contributor on $AccountName")) {
            Invoke-AzCliJson -Arguments @(
                "cosmosdb", "sql", "role", "assignment", "create",
                "--subscription", $SubscriptionId,
                "--resource-group", $ResourceGroupName,
                "--account-name", $AccountName,
                "--role-definition-id", $dataContributorRoleDefinitionId,
                "--principal-id", $principalId,
                "--scope", $effectiveDataPlaneScope
            ) | Out-Null
            $dataContributorStatus = "Created"
        }
        else {
            $dataContributorStatus = "WhatIf"
        }
    }

    $cosmosOperatorStatus = "Skipped"
    if (-not $SkipCosmosOperatorRole) {
        $managementAssignments = @(Invoke-AzCliJson -Arguments @(
            "role", "assignment", "list",
            "--scope", $cosmosAccountId,
            "--include-inherited"
        ))

        $existingManagementAssignment = $managementAssignments | Where-Object {
            $_.principalId -eq $principalId -and
            $_.roleDefinitionId -eq $cosmosOperatorRoleDefinitionId
        } | Select-Object -First 1

        $cosmosOperatorStatus = "AlreadyExists"
        if (-not $existingManagementAssignment) {
            if ($PSCmdlet.ShouldProcess($principalId, "Assign $cosmosOperatorRoleName on $AccountName")) {
                Invoke-AzCliJson -Arguments @(
                    "role", "assignment", "create",
                    "--assignee-object-id", $principalId,
                    "--assignee-principal-type", $PrincipalType,
                    "--role", $cosmosOperatorRoleDefinitionId,
                    "--scope", $cosmosAccountId
                ) | Out-Null
                $cosmosOperatorStatus = "Created"
            }
            else {
                $cosmosOperatorStatus = "WhatIf"
            }
        }
    }

    [pscustomobject]@{
        Identity = $identity
        PrincipalId = $principalId
        CosmosDataContributor = $dataContributorStatus
        CosmosDbOperator = $cosmosOperatorStatus
        AccountName = $AccountName
        DataPlaneScope = $effectiveDataPlaneScope
    }
}

$results | Format-Table -AutoSize
