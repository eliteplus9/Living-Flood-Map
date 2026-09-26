$ErrorActionPreference = 'Stop'
$classifierRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent $classifierRoot
New-Item -ItemType Directory -Force "$classifierRoot/runtime/src", "$classifierRoot/runtime/models" | Out-Null
foreach ($module in @('__init__.py', 'classify.py', 'data.py', 'text_model.py', 'geocode.py', 'locations.py')) {
    Copy-Item -LiteralPath "$repoRoot/src/$module" -Destination "$classifierRoot/runtime/src/$module"
}
Copy-Item -LiteralPath "$repoRoot/models/relevance.json.gz" -Destination "$classifierRoot/runtime/models/relevance.json.gz"
