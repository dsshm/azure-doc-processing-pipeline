<#
.SYNOPSIS
Grants one or more Microsoft Entra principals Azure Storage Blob data-plane access.

.DESCRIPTION
Assigns a Storage Blob Data Reader, Contributor, or Owner role at the storage account
scope by default. Optionally scopes the assignment to a single blob container.

Azure Owner/Contributor roles grant management-plane access only; they do not allow
portal or SDK data-plane access to list, read, upload, or delete blobs when shared
key access is disabled.

.EXAMPLE
.\scripts\Grant-StorageBlobDataAccess.ps1 -User user1@contoso.com,user2@contoso.com

.EXAMPLE
.\scripts\Grant-StorageBlobDataAccess.ps1 -User 00000000-0000-0000-0000-000000000000 -Role Contributor
#>

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter()]
    [string]$SubscriptionId = "9698dd71-9367-49c2-bede-fd0deecfad62",

    [Parameter()]
    [string]$ResourceGroupName = "rg-docpipeline-maps-test",

    [Parameter()]
    [string]$StorageAccountName = "stdocpipelinejd7zqs",

    [Parameter(Mandatory = $true)]
    [Alias("Users")]
    [string[]]$User,

    [Parameter()]
    [ValidateSet("User", "Group", "ServicePrincipal")]
    [string]$PrincipalType = "User",

    [Parameter()]
    [ValidateSet("Reader", "Contributor", "Owner")]
    [string]$Role = "Reader",

    [Parameter()]
    [string]$ContainerName = ""
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

$roleName = "Storage Blob Data $Role"

Invoke-AzCli -Arguments @("account", "set", "--subscription", $SubscriptionId) | Out-Null

$storageAccountId = (Invoke-AzCli -Arguments @(
    "storage", "account", "show",
    "--subscription", $SubscriptionId,
    "--resource-group", $ResourceGroupName,
    "--name", $StorageAccountName,
    "--query", "id",
    "-o", "tsv"
) | Select-Object -First 1).Trim()

$effectiveScope = if ([string]::IsNullOrWhiteSpace($ContainerName)) {
    $storageAccountId
}
else {
    "$storageAccountId/blobServices/default/containers/$ContainerName"
}

$results = foreach ($identity in $User) {
    $principalId = Resolve-PrincipalId -Identity $identity

    $existingAssignments = @(Invoke-AzCliJson -Arguments @(
        "role", "assignment", "list",
        "--scope", $effectiveScope,
        "--include-inherited"
    ))

    $existingAssignment = $existingAssignments | Where-Object {
        $_.principalId -eq $principalId -and
        $_.roleDefinitionName -eq $roleName
    } | Select-Object -First 1

    $status = "AlreadyExists"
    if (-not $existingAssignment) {
        if ($PSCmdlet.ShouldProcess($principalId, "Assign $roleName on $effectiveScope")) {
            Invoke-AzCliJson -Arguments @(
                "role", "assignment", "create",
                "--assignee-object-id", $principalId,
                "--assignee-principal-type", $PrincipalType,
                "--role", $roleName,
                "--scope", $effectiveScope
            ) | Out-Null
            $status = "Created"
        }
        else {
            $status = "WhatIf"
        }
    }

    [pscustomobject]@{
        Identity = $identity
        PrincipalId = $principalId
        Role = $roleName
        Status = $status
        StorageAccountName = $StorageAccountName
        Scope = $effectiveScope
    }
}

$results | Format-Table -AutoSize
