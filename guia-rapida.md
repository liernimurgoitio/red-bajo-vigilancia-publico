# Guía rápida de uso y mantenimiento

## Dónde se ejecuta cada cosa

| Tarea | Equipo |
| --- | --- |
| Consultar el router, servir el panel y guardar el historial | Raspberry Pi |
| Crear una copia diaria entre las 03:00 y las 03:15 | Raspberry Pi |
| Descargar copias al iniciar sesión y cada hora | Windows, con la sesión abierta |
| Consultar el panel desde fuera de casa | Android con Tailscale y acceso a Internet |
| Laboratorio SSH aislado | Ubuntu en VMware, separado de la red doméstica |

El panel y las copias de la Raspberry funcionan con el PC apagado. Para la copia externa automática hace falta que Windows esté encendido y pueda conectarse con la Raspberry. La carpeta externa conserva los archivos anteriores aunque dejen de estar entre las siete copias de la microSD.

## Volver a conectar desde Windows

En PowerShell, sustituyendo la dirección por la de mi Raspberry:

```powershell
ssh -i "$env:USERPROFILE\.ssh\red-vigilancia-pi" admin-lab@DIRECCION_RASPBERRY
```

El indicador `PS C:\...>` corresponde a Windows. El indicador `admin-lab@red-vigilancia` corresponde a la Raspberry. Para salir de SSH escribo `exit`; esto no apaga la Raspberry ni detiene el panel.

## Si el panel no responde

Primero compruebo que la Raspberry está alimentada y conectada a la red. Dentro de su terminal consulto:

```bash
systemctl is-active red-vigilancia.service
sudo journalctl -u red-vigilancia.service -n 25 --no-pager
```

Si aparecen errores de consulta, compruebo primero el cable o el Wi-Fi. La prueba controlada del 18 de noviembre ha confirmado que el programa vuelve a consultar después de recuperar la conexión. Un error de autenticación requiere revisar el acceso al router; no todos los errores tienen la misma causa.

Si necesito reiniciar únicamente el programa:

```bash
sudo systemctl restart red-vigilancia.service
```

## Revisar las copias de la Raspberry

```bash
systemctl list-timers red-vigilancia-backup.timer --no-pager
sudo journalctl -u red-vigilancia-backup.service --since today --no-pager
```

Después de una copia correcta, `Deactivated successfully` es normal: la tarea de copia termina, mientras el temporizador espera la siguiente ejecución.

## Revisar las copias externas desde Windows

```powershell
Get-Content "$env:USERPROFILE\Documents\Copias Raspberry\resultado-copias.log" -Tail 5
Get-ScheduledTaskInfo -TaskName "Red bajo vigilancia - copia externa"
```

Un mensaje con cero copias nuevas es correcto cuando los archivos disponibles ya estaban descargados y verificados. Si falla el acceso automático, compruebo si la dirección de la Raspberry ha cambiado y si el agente SSH dispone de la clave. No guardo su frase de contraseña en un programa.

## Apagar la Raspberry

Si necesito desconectarla de la corriente, primero ejecuto en su terminal:

```bash
sudo poweroff
```

Espero a que termine el apagado antes de retirar la alimentación. No utilizo un corte de corriente como prueba de recuperación.

Las instrucciones completas de copias y sus límites están en [copias-seguridad.md](copias-seguridad.md). Las pruebas realizadas están en [servidor-raspberry-pi.md](servidor-raspberry-pi.md) y [pruebas-automaticas.md](pruebas-automaticas.md).
