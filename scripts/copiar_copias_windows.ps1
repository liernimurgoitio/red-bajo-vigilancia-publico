param(
    [Parameter(Mandatory = $true)][string]$Servidor,
    [string]$Usuario = 'admin-lab',
    [string]$Clave = "$env:USERPROFILE\.ssh\red-vigilancia-pi",
    [string]$Destino = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Copias Raspberry')
)
$ErrorActionPreference = 'Stop'
if ($Servidor -notmatch '^[a-zA-Z0-9.-]+$' -or $Usuario -notmatch '^[a-zA-Z0-9_-]+$') {
    throw 'Servidor o usuario no validos.'
}
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$registro = Join-Path $Destino 'resultado-copias.log'
$bloqueo = $null
$temporal = $null
function Registrar([string]$Mensaje) {
    $linea = ('{0} | {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Mensaje)
    Add-Content -LiteralPath $registro -Value $linea -Encoding UTF8
    Write-Output $linea
}
try {
    try {
        $bloqueo = [IO.File]::Open((Join-Path $Destino '.copia-en-curso'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch [IO.IOException] { exit 0 }
    $ssh = (Get-Command ssh.exe -ErrorAction Stop).Source
    $scp = (Get-Command scp.exe -ErrorAction Stop).Source
    $opciones = @('-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','-o','StrictHostKeyChecking=yes','-o','IdentitiesOnly=yes','-i',$Clave)
    $equipo = "${Usuario}@${Servidor}"
    $listado = @(& $ssh @opciones $equipo 'find /var/lib/red-vigilancia-copias -maxdepth 1 -type f -name ''copia-red-*.tar.gz.sha256'' -printf ''%f\n''' 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'No se ha podido conectar. Se reintentara en la siguiente ejecucion.' }
    $nombres = @($listado | ForEach-Object { "$_" } | Where-Object { $_ -match '^copia-red-\d{8}T\d{6}-[a-f0-9]{8}\.tar\.gz\.sha256$' })
    if ($nombres.Count -eq 0) { throw 'El servidor no ha devuelto copias verificables.' }
    $temporal = Join-Path $Destino ('.descarga-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temporal | Out-Null
    $nuevas = 0
    foreach ($sello in $nombres) {
        $nombre = $sello.Substring(0, $sello.Length - 7)
        $salida = @(& $scp @opciones "${equipo}:/var/lib/red-vigilancia-copias/$sello" (Join-Path $temporal $sello) 2>&1)
        if ($LASTEXITCODE -ne 0) { throw 'No se ha podido descargar la comprobacion de una copia.' }
        $texto = [IO.File]::ReadAllText((Join-Path $temporal $sello)).Trim()
        if ($texto -notmatch '^([a-fA-F0-9]{64})\s+(.+)$' -or $Matches[2] -ne $nombre) { throw 'Formato de comprobacion no valido.' }
        $esperado = $Matches[1]
        $archivo = Join-Path $Destino $nombre
        if ((Test-Path -LiteralPath $archivo) -and (Get-FileHash -LiteralPath $archivo -Algorithm SHA256).Hash -eq $esperado) { continue }
        $parcial = Join-Path $temporal $nombre
        $salida = @(& $scp @opciones "${equipo}:/var/lib/red-vigilancia-copias/$nombre" $parcial 2>&1)
        if ($LASTEXITCODE -ne 0) { throw 'La descarga de una copia no ha terminado.' }
        if ((Get-FileHash -LiteralPath $parcial -Algorithm SHA256).Hash -ne $esperado) { throw 'La copia descargada no coincide con su comprobacion.' }
        Move-Item -LiteralPath $parcial -Destination $archivo -Force
        Move-Item -LiteralPath (Join-Path $temporal $sello) -Destination (Join-Path $Destino $sello) -Force
        $nuevas++
    }
    Registrar "Correcto. Copias nuevas descargadas y verificadas: $nuevas."
    exit 0
} catch {
    Registrar "ERROR: $($_.Exception.Message)"
    exit 1
} finally {
    if ($temporal -and (Test-Path -LiteralPath $temporal)) {
        # Solo eliminar los archivos directos de la carpeta temporal creada en esta ejecucion.
        Get-ChildItem -LiteralPath $temporal -File | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
        Remove-Item -LiteralPath $temporal -Force
    }
    if ($bloqueo) { $bloqueo.Dispose() }
}
