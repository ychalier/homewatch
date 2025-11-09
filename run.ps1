$pythonPath = "python"
$scriptPath = "homewatch.py"
$scriptArgs = @("runserver")

$restartCode = 42

do {
    Write-Host "Running Homewatch..."
    & $pythonPath $scriptPath @scriptArgs
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq $restartCode) {
        Write-Host "Restarting..."
        Start-Sleep -Seconds 2
    }
} while ($exitCode -eq $restartCode)
