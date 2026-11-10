# Ejecutar desde PowerShell: .\probar_postgresql.ps1
# Django crea una base separada para las pruebas; no migra buildcorp.
$clavePruebas = Read-Host 'Contraseña de la cuenta PostgreSQL' -AsSecureString
$claveAnterior = $env:PGPASSWORD
try {
    $env:PGPASSWORD = [System.Net.NetworkCredential]::new('', $clavePruebas).Password
    $pythonPruebas = Join-Path $PSScriptRoot 'env\Scripts\python.exe'
    $verificadorPruebas = Join-Path $PSScriptRoot 'verificar_postgresql.py'
    # La captura se realiza en Python: stderr normal de Django no se
    # interpreta como un error de PowerShell. Se conserva el código de salida.
    & $pythonPruebas -u $verificadorPruebas
    if ($LASTEXITCODE -ne 0) {
        throw 'La comprobación no terminó correctamente. Revisa pruebas-postgresql.log.'
    }
} finally {
    $env:PGPASSWORD = $claveAnterior
    Remove-Variable clavePruebas, claveAnterior
}
