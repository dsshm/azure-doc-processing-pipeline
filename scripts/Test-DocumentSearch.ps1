<#
.SYNOPSIS
Tests Cosmos DB full-text, vector, and hybrid document search for a phrase.

.DESCRIPTION
Generates an Azure OpenAI embedding when the selected mode needs a query vector,
then runs the same Cosmos DB for NoSQL query shapes used by the document pipeline:
FullTextContainsAny/FullTextScore for full-text search, VectorDistance for
vector search, and RRF for hybrid ranking.

The script uses Azure CLI to obtain Microsoft Entra tokens. No Cosmos keys or
Azure OpenAI keys are required.

.EXAMPLE
.\scripts\Test-DocumentSearch.ps1 -Query "nashville" -ResourceGroupName rg-docpipeline-maps-test

.EXAMPLE
.\scripts\Test-DocumentSearch.ps1 -Query "Beverly Hills" -ResourceGroupName rg-docpipeline-maps-test -Mode All -Top 5
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$Query,

    [Parameter()]
    [string]$SubscriptionId = "",

    [Parameter()]
    [string]$ResourceGroupName = "",

    [Parameter()]
    [string]$CosmosAccountName = "",

    [Parameter()]
    [string]$CosmosEndpoint = "",

    [Parameter()]
    [string]$OpenAIAccountName = "",

    [Parameter()]
    [string]$OpenAIEndpoint = "",

    [Parameter()]
    [string]$DatabaseName = "docprocessing",

    [Parameter()]
    [string]$ContainerName = "results",

    [Parameter()]
    [string]$EmbeddingDeployment = "text-embedding-3-small",

    [Parameter()]
    [Alias("OpenAIApiVersion")]
    [string]$EmbeddingApiVersion = "2024-12-01-preview",

    [Parameter()]
    [ValidateSet("All", "FullText", "Vector", "Hybrid", "Chunks")]
    [string]$Mode = "All",

    [Parameter()]
    [ValidateSet("summary_vector", "purpose_vector")]
    [string]$VectorField = "summary_vector",

    [Parameter()]
    [ValidateRange(1, 1000)]
    [int]$Top = 10,

    [Parameter()]
    [double]$MaxVectorDistance = [double]::NaN,

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

function Get-AzAccessToken {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Resource
    )

    $token = Invoke-AzCli -Arguments @(
        "account", "get-access-token",
        "--resource", $Resource,
        "--query", "accessToken",
        "-o", "tsv"
    )

    return (($token -join "")).Trim()
}

function Join-Url {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BaseUrl,

        [Parameter(Mandatory = $true)]
        [string]$RelativePath
    )

    return "$($BaseUrl.TrimEnd('/'))/$($RelativePath.TrimStart('/'))"
}

function Resolve-CosmosEndpoint {
    if (-not [string]::IsNullOrWhiteSpace($CosmosEndpoint)) {
        return $CosmosEndpoint
    }

    if ([string]::IsNullOrWhiteSpace($ResourceGroupName)) {
        throw "Provide -CosmosEndpoint, or provide -ResourceGroupName so the Cosmos account can be discovered."
    }

    $resolvedAccountName = $CosmosAccountName
    if ([string]::IsNullOrWhiteSpace($resolvedAccountName)) {
        $names = @(Invoke-AzCli -Arguments @(
            "cosmosdb", "list",
            "--resource-group", $ResourceGroupName,
            "--query", "[].name",
            "-o", "tsv"
        ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

        if ($names.Count -ne 1) {
            throw "Found $($names.Count) Cosmos DB accounts in resource group '$ResourceGroupName'. Specify -CosmosAccountName."
        }
        $resolvedAccountName = $names[0].Trim()
    }

    $endpoint = Invoke-AzCli -Arguments @(
        "cosmosdb", "show",
        "--resource-group", $ResourceGroupName,
        "--name", $resolvedAccountName,
        "--query", "documentEndpoint",
        "-o", "tsv"
    )
    return (($endpoint -join "")).Trim()
}

function Resolve-OpenAIEndpoint {
    if (-not [string]::IsNullOrWhiteSpace($OpenAIEndpoint)) {
        return $OpenAIEndpoint
    }

    if ([string]::IsNullOrWhiteSpace($ResourceGroupName)) {
        throw "Provide -OpenAIEndpoint, or provide -ResourceGroupName so the Azure OpenAI account can be discovered."
    }

    $resolvedAccountName = $OpenAIAccountName
    if ([string]::IsNullOrWhiteSpace($resolvedAccountName)) {
        $names = @(Invoke-AzCli -Arguments @(
            "cognitiveservices", "account", "list",
            "--resource-group", $ResourceGroupName,
            "--query", "[?kind=='OpenAI'].name",
            "-o", "tsv"
        ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })

        if ($names.Count -ne 1) {
            throw "Found $($names.Count) Azure OpenAI accounts in resource group '$ResourceGroupName'. Specify -OpenAIAccountName."
        }
        $resolvedAccountName = $names[0].Trim()
    }

    $endpoint = Invoke-AzCli -Arguments @(
        "cognitiveservices", "account", "show",
        "--resource-group", $ResourceGroupName,
        "--name", $resolvedAccountName,
        "--query", "properties.endpoint",
        "-o", "tsv"
    )
    return (($endpoint -join "")).Trim()
}

function New-SearchTerms {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $terms = [System.Collections.Generic.List[string]]::new()
    $seen = @{}

    function Add-Term {
        param([string]$Value)
        $normalized = $Value.Trim()
        $key = $normalized.ToLowerInvariant()
        if ($normalized.Length -gt 0 -and -not $seen.ContainsKey($key)) {
            $terms.Add($normalized)
            $seen[$key] = $true
        }
    }

    Add-Term -Value $Text
    foreach ($match in [regex]::Matches($Text, "[\p{L}\p{N}_][\p{L}\p{N}_'-]*")) {
        if ($terms.Count -ge 12) {
            break
        }
        if ($match.Value.Length -gt 1) {
            Add-Term -Value $match.Value
        }
    }

    return @($terms)
}

function New-TermParameters {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Terms
    )

    $parameters = @()
    for ($index = 0; $index -lt $Terms.Count; $index++) {
        $parameters += @{
            name = "@term$index"
            value = $Terms[$index]
        }
    }
    return $parameters
}

function Invoke-Embedding {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Endpoint,

        [Parameter(Mandatory = $true)]
        [string]$AccessToken,

        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $uri = Join-Url -BaseUrl $Endpoint -RelativePath "openai/deployments/$EmbeddingDeployment/embeddings?api-version=$EmbeddingApiVersion"
    $body = @{ input = $Text } | ConvertTo-Json -Depth 10
    $headers = @{
        Authorization = "Bearer $AccessToken"
        "Content-Type" = "application/json"
    }

    try {
        $response = Invoke-RestMethod -Method Post -Uri $uri -Headers $headers -Body $body
    }
    catch {
        $details = $_.ErrorDetails.Message
        if ([string]::IsNullOrWhiteSpace($details)) {
            $details = $_.Exception.Message
        }

        throw "Azure OpenAI embedding request failed. Confirm the caller has 'Cognitive Services OpenAI User' on the Azure OpenAI account and that this host can reach the Azure OpenAI endpoint if public network access is disabled.`n$details"
    }

    $data = @($response.data)
    if ($data.Count -lt 1 -or -not $data[0].embedding) {
        throw "Azure OpenAI embedding response did not include data[0].embedding."
    }

    return @($data[0].embedding)
}

function Invoke-CosmosQuery {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Endpoint,

        [Parameter(Mandatory = $true)]
        [string]$Sql,

        [Parameter(Mandatory = $true)]
        [object[]]$Parameters
    )

    $payload = @{
        endpoint = $Endpoint
        database = $DatabaseName
        container = $ContainerName
        query = $Sql
        parameters = $Parameters
    } | ConvertTo-Json -Depth 100 -Compress

    $payloadPath = Join-Path ([System.IO.Path]::GetTempPath()) ("cosmos-query-{0}.json" -f ([Guid]::NewGuid().ToString("N")))
    $scriptPath = Join-Path ([System.IO.Path]::GetTempPath()) ("cosmos-query-{0}.py" -f ([Guid]::NewGuid().ToString("N")))
    $errorPath = Join-Path ([System.IO.Path]::GetTempPath()) ("cosmos-query-{0}.err" -f ([Guid]::NewGuid().ToString("N")))

    $pythonScript = @'
import json
import sys

from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential

with open(sys.argv[1], "r", encoding="utf-8") as payload_file:
    payload = json.load(payload_file)

credential = DefaultAzureCredential()
client = CosmosClient(payload["endpoint"], credential=credential)
container = client.get_database_client(payload["database"]).get_container_client(payload["container"])
items = list(container.query_items(
    query=payload["query"],
    parameters=payload["parameters"],
    enable_cross_partition_query=True,
))
print(json.dumps(items))
'@

    try {
        Set-Content -LiteralPath $payloadPath -Value $payload -Encoding UTF8
        Set-Content -LiteralPath $scriptPath -Value $pythonScript -Encoding UTF8

        $output = & python $scriptPath $payloadPath 2> $errorPath
        if ($LASTEXITCODE -ne 0) {
            $errorText = if (Test-Path -LiteralPath $errorPath) { Get-Content -Raw -Path $errorPath } else { "" }
            throw "Cosmos SDK query failed:`n$($output -join [Environment]::NewLine)`n$errorText"
        }

        $json = ($output -join [Environment]::NewLine).Trim()
        if ([string]::IsNullOrWhiteSpace($json)) {
            return @()
        }

        $items = $json | ConvertFrom-Json
        if ($null -eq $items) {
            return @()
        }

        return @($items)
    }
    finally {
        foreach ($path in @($payloadPath, $scriptPath, $errorPath)) {
            if (Test-Path -LiteralPath $path) {
                Remove-Item -LiteralPath $path -Force
            }
        }
    }
}

function Select-VectorDistance {
    param([object]$Item)

    if ($Item.PSObject.Properties.Name -contains "score") {
        return $Item.score
    }
    if ($Item.PSObject.Properties.Name -contains "vector_score") {
        return $Item.vector_score
    }
    return $null
}

function Limit-ByVectorDistance {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Items
    )

    if ([double]::IsNaN($MaxVectorDistance)) {
        return $Items
    }

    return @($Items | Where-Object {
        $distance = Select-VectorDistance -Item $_
        $null -ne $distance -and [double]$distance -le $MaxVectorDistance
    })
}

function Write-SearchResults {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$Items
    )

    Write-Host ""
    Write-Host "[$Name] $($Items.Count) result(s)"

    if ($RawJson) {
        $Items | ConvertTo-Json -Depth 50
        return
    }

    if ($Items.Count -eq 0) {
        return
    }

    $Items |
        Select-Object `
            id,
            jobId,
            title,
            doc_type,
            @{ Name = "score"; Expression = { Select-VectorDistance -Item $_ } },
            document_purpose |
        Format-Table -AutoSize
}

function Test-NeedsEmbedding {
    param([string]$SearchMode)

    return $SearchMode -in @("All", "Vector", "Hybrid", "Chunks")
}

function Assert-PythonCosmosDependencies {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python is required for Cosmos SDK queries. Install Python and run 'pip install -r requirements.txt'."
    }

    $output = & python -c "import azure.cosmos, azure.identity" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python packages azure-cosmos and azure-identity are required. Run 'pip install -r requirements.txt'.`n$($output -join [Environment]::NewLine)"
    }
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI (az) is required."
}

Assert-PythonCosmosDependencies

if (-not [string]::IsNullOrWhiteSpace($SubscriptionId)) {
    Invoke-AzCli -Arguments @("account", "set", "--subscription", $SubscriptionId) | Out-Null
}

$normalizedQuery = $Query.Trim()
if ([string]::IsNullOrWhiteSpace($normalizedQuery)) {
    throw "Query must not be empty."
}

$needsEmbedding = Test-NeedsEmbedding -SearchMode $Mode
$effectiveCosmosEndpoint = Resolve-CosmosEndpoint
$effectiveOpenAIEndpoint = if ($needsEmbedding) { Resolve-OpenAIEndpoint } else { "" }
$terms = New-SearchTerms -Text $normalizedQuery
$termParameters = @(New-TermParameters -Terms $terms)
$termArguments = ($termParameters | ForEach-Object { $_.name }) -join ", "

Write-Host "Query: $normalizedQuery"
Write-Host "Cosmos endpoint: $effectiveCosmosEndpoint"
if ($needsEmbedding) {
    Write-Host "Azure OpenAI endpoint: $effectiveOpenAIEndpoint"
}
Write-Host "Search terms: $($terms -join ', ')"

$queryVector = @()
if ($needsEmbedding) {
    $openAiToken = Get-AzAccessToken -Resource "https://cognitiveservices.azure.com/"
    Write-Host "Generating embedding with deployment '$EmbeddingDeployment'..."
    $queryVector = Invoke-Embedding -Endpoint $effectiveOpenAIEndpoint -AccessToken $openAiToken -Text $normalizedQuery
    Write-Host "Embedding dimensions: $($queryVector.Count)"
}

if ($Mode -in @("All", "FullText")) {
    $fullTextSql = @"
SELECT TOP $Top c.id, c.jobId, c.title, c.doc_type, c.summary, c.search_text,
  c.key_fields.document_purpose AS document_purpose,
  c.key_fields.entities.geocoded_locations AS geocoded_locations
FROM c
WHERE IS_DEFINED(c.search_text)
  AND FullTextContainsAny(c.search_text, $termArguments)
ORDER BY RANK FullTextScore(c.search_text, $termArguments)
"@
    $results = @(Invoke-CosmosQuery -Endpoint $effectiveCosmosEndpoint -Sql $fullTextSql -Parameters $termParameters)
    Write-SearchResults -Name "Full-text" -Items $results
}

if ($Mode -in @("All", "Vector")) {
    $vectorSql = @"
SELECT TOP $Top c.id, c.jobId, c.title, c.doc_type, c.summary, c.search_text,
  c.key_fields.document_purpose AS document_purpose,
  c.key_fields.entities.geocoded_locations AS geocoded_locations,
  VectorDistance(c.$VectorField, @queryVector) AS score
FROM c
WHERE IS_DEFINED(c.$VectorField)
ORDER BY VectorDistance(c.$VectorField, @queryVector)
"@
    $parameters = @(@{ name = "@queryVector"; value = $queryVector })
    $results = @(Invoke-CosmosQuery -Endpoint $effectiveCosmosEndpoint -Sql $vectorSql -Parameters $parameters)
    $results = Limit-ByVectorDistance -Items $results
    Write-SearchResults -Name "Vector ($VectorField)" -Items $results
}

if ($Mode -in @("All", "Hybrid")) {
    $hybridSql = @"
SELECT TOP $Top c.id, c.jobId, c.title, c.doc_type, c.summary, c.search_text,
  c.key_fields.document_purpose AS document_purpose,
  c.key_fields.entities.geocoded_locations AS geocoded_locations,
  VectorDistance(c.$VectorField, @queryVector) AS vector_score
FROM c
WHERE IS_DEFINED(c.$VectorField)
  AND IS_DEFINED(c.search_text)
  AND FullTextContainsAny(c.search_text, $termArguments)
ORDER BY RANK RRF(VectorDistance(c.$VectorField, @queryVector), FullTextScore(c.search_text, $termArguments), [2, 1])
"@
    $parameters = @(@{ name = "@queryVector"; value = $queryVector }) + $termParameters
    $results = @(Invoke-CosmosQuery -Endpoint $effectiveCosmosEndpoint -Sql $hybridSql -Parameters $parameters)
    $results = Limit-ByVectorDistance -Items $results
    Write-SearchResults -Name "Hybrid ($VectorField, requires full-text match)" -Items $results
}

if ($Mode -in @("All", "Chunks")) {
    $chunkSql = @"
SELECT TOP $Top c.id, c.jobId, c.title, c.doc_type,
  chunk.chunk_index, chunk.text AS chunk_text,
  VectorDistance(chunk.vector, @queryVector) AS score
FROM c JOIN chunk IN c.chunks
WHERE c.chunks != null
ORDER BY VectorDistance(chunk.vector, @queryVector)
"@
    $parameters = @(@{ name = "@queryVector"; value = $queryVector })
    $results = @(Invoke-CosmosQuery -Endpoint $effectiveCosmosEndpoint -Sql $chunkSql -Parameters $parameters)
    $results = Limit-ByVectorDistance -Items $results
    Write-SearchResults -Name "Chunks" -Items $results
}
