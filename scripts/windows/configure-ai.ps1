$ErrorActionPreference = "Stop"

Write-Host "TCG Resale Evaluator - automatic recommendations" -ForegroundColor Cyan
Write-Host "Paste your OpenAI API key. It will be stored as a private user environment variable."
$SecureKey = Read-Host "OpenAI API key" -AsSecureString
$Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
try {
    $PlainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer)
    if ([string]::IsNullOrWhiteSpace($PlainKey)) {
        throw "No API key was entered."
    }
    [Environment]::SetEnvironmentVariable("OPENAI_API_KEY", $PlainKey, "User")
    [Environment]::SetEnvironmentVariable("TCG_AI_ENABLED", "1", "User")
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
    $PlainKey = $null
}

Write-Host "Automatic recommendations are enabled." -ForegroundColor Green
Write-Host "Close and reopen the TCG Resale Evaluator. Completed lots will be evaluated automatically."
