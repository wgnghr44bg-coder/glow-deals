# Haalt de prijzen op en zet ze op de site (GitHub Pages).
# Draait via de Windows-taak "Glow Deals prijzen" op de pc van de eigenaar; het log staat in bijwerken.log.
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$log = Join-Path $PSScriptRoot "bijwerken.log"
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm') ===" | Out-File $log -Append -Encoding utf8

git pull --rebase -q 2>&1 | Out-File $log -Append -Encoding utf8
python -u update.py 2>&1 | Out-File $log -Append -Encoding utf8

git add docs/data.json
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -q -m "Prijzen bijgewerkt $(Get-Date -Format 'yyyy-MM-dd HH:mm')" 2>&1 | Out-File $log -Append -Encoding utf8
    git push -q 2>&1 | Out-File $log -Append -Encoding utf8
    "online gezet" | Out-File $log -Append -Encoding utf8
} else {
    "geen nieuwe prijzen" | Out-File $log -Append -Encoding utf8
}
