# Ejecutar desde PowerShell: .\configurar_postgresql.ps1
# La contraseña queda solo en esta sesión. Al abrir otra terminal, repetir.
$clavePostgres = Read-Host 'Contraseña de postgres' -AsSecureString
$env:PGPASSWORD = [System.Net.NetworkCredential]::new('', $clavePostgres).Password
Remove-Variable clavePostgres

$pythonProyecto = Join-Path $PSScriptRoot 'env\Scripts\python.exe'
$manageProyecto = Join-Path $PSScriptRoot 'manage.py'

# migrate comprueba el acceso y crea las tablas pendientes en buildcorp.
& $pythonProyecto $manageProyecto migrate --noinput
if ($LASTEXITCODE -ne 0) {
    Write-Error 'No se completaron las migraciones. Revisa la contraseña y la conexión.'
    return
}
& $pythonProyecto $manageProyecto check --database default
