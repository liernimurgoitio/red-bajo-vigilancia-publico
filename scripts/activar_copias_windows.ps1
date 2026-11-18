param([Parameter(Mandatory = $true)][string]$Servidor)
$ErrorActionPreference = 'Stop'
if ($Servidor -notmatch '^[a-zA-Z0-9.-]+$') { throw 'Servidor no valido.' }
$script = Join-Path $PSScriptRoot 'copiar_copias_windows.ps1'
if (-not (Test-Path -LiteralPath $script)) { throw 'Falta el programa de copia.' }
$usuario = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$ejecutable = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$argumentos = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}" -Servidor "{1}"' -f $script, $Servidor
$accion = New-ScheduledTaskAction -Execute $ejecutable -Argument $argumentos
$inicio = New-ScheduledTaskTrigger -AtLogOn -User $usuario
$hora = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
$opciones = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId $usuario -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'Red bajo vigilancia - copia externa' -Description 'Descarga copias verificadas de la Raspberry al iniciar sesion y cada hora. No elimina las copias conservadas en Windows.' -Action $accion -Trigger @($inicio,$hora) -Settings $opciones -Principal $principal -Force | Select-Object TaskName,State
