param(
    [Parameter(Mandatory=$true)][string]$Endpoint,
    [ValidateSet('GET','POST','PATCH','PUT')][string]$Method = 'GET',
    [string]$BodyFile
)

$ErrorActionPreference = 'Stop'
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
$credential = "protocol=https`nhost=github.com`n`n" | git credential fill 2>$null
if ($LASTEXITCODE -ne 0) { throw 'GitHub authentication is unavailable' }
$fields = @{}
foreach ($line in $credential) {
    $pair = $line -split '=', 2
    if ($pair.Length -eq 2) { $fields[$pair[0]] = $pair[1] }
}
$headers = @{
    Authorization = 'Bearer ' + $fields['password']
    Accept = 'application/vnd.github+json'
    'X-GitHub-Api-Version' = '2022-11-28'
}
$parameters = @{
    Uri = 'https://api.github.com/' + $Endpoint.TrimStart('/')
    Method = $Method
    Headers = $headers
}
if ($BodyFile) {
    $parameters.Body = Get-Content -LiteralPath $BodyFile -Raw
    $parameters.ContentType = 'application/json'
}
try {
    $result = Invoke-RestMethod @parameters
    $result | ConvertTo-Json -Depth 20
} catch {
    $status = [int]$_.Exception.Response.StatusCode
    Write-Output ('GitHub API status: ' + $status)
    exit 1
}
