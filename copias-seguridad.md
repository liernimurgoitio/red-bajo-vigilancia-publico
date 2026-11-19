# Copias privadas del servidor

El 17 de noviembre de 2026 he creado y verificado la primera copia en la Raspberry. He activado el temporizador diario y he comprobado que la siguiente ejecución ha quedado programada para el 18 de noviembre a las 03:08 CET. También he transferido una copia a Windows para conservarla fuera de la microSD. El 18 de noviembre he comprobado la primera ejecución automática: ha comenzado a las 03:08:34 CET y ha terminado correctamente a las 03:08:35. También he extraído la copia manual en una carpeta privada de prueba: todas las sumas SHA-256 han coincidido, el inventario se ha podido leer y SQLite ha devuelto «ok» en la comprobación de integridad. Esta prueba verifica la extracción y lectura de los datos. Además, he comprobado automáticamente el arranque de un servidor separado desde una copia con datos ficticios y un router simulado; todavía no he arrancado otra Raspberry con la copia real.

## Qué conserva

- Inventario privado, asociaciones y claves de vinculación de TV.
- Historial SQLite, capturado mediante la API de copias para poder leerlo mientras el panel funciona.
- Fotos, panel, programas, documentación y archivos de instalación del proyecto.
- Configuración privada de Tailscale y las tres credenciales del servicio.

El archivo incluye secretos y no está cifrado. Solo el propietario puede acceder a su carpeta en Linux. No debe publicarse en GitHub ni compartirse como una captura del proyecto.

El programa comprueba que el inventario sea JSON válido, verifica la copia de SQLite y relee el archivo para comprobar las sumas SHA-256 antes de eliminar copias antiguas. Conserva las siete copias más recientes. Las sumas ayudan a detectar daños; no sustituyen al cifrado ni demuestran autenticidad ante una modificación maliciosa.

## Activar en la Raspberry

Después de copiar estos archivos al proyecto del servidor:

```bash
cd ~/red-bajo-vigilancia
sudo install -m 644 red-vigilancia-backup.service red-vigilancia-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start red-vigilancia-backup.service
sudo systemctl status red-vigilancia-backup.service --no-pager
```

Si la primera copia termina correctamente:

```bash
sudo systemctl enable --now red-vigilancia-backup.timer
systemctl list-timers red-vigilancia-backup.timer --no-pager
```

La copia diaria se programa a las 03:00, con un retraso aleatorio de hasta quince minutos, en el horario del servidor. Si la Raspberry ha estado apagada durante una ejecución, el temporizador persistente recupera una ejecución pendiente al arrancar.

Las copias se guardan en `/var/lib/red-vigilancia-copias`. Para revisar la última ejecución:

```bash
sudo journalctl -u red-vigilancia-backup.service -n 20 --no-pager
ls -lh /var/lib/red-vigilancia-copias
```

## Conservar una copia fuera de la tarjeta

Estas copias están en la misma microSD. Ayudan ante cambios accidentales, pero no protegen frente al fallo de esa tarjeta. Debe conservarse además una copia en otro equipo o disco, con acceso restringido. El 18 de noviembre de 2026 he activado una tarea en Windows para descargar las copias al iniciar sesión y cada hora mientras la cuenta de Windows esté abierta. He comprobado una descarga real de dos archivos y una ejecución posterior de la tarea, que ha terminado con resultado 0 sin volver a descargar las copias correctas. He reiniciado Windows y he comprobado una nueva ejecución correcta a las 15:05:04 del 18 de noviembre, sin conectarme antes por SSH ni ejecutar de nuevo ssh-add. El registro ha indicado cero copias nuevas porque los archivos disponibles ya estaban guardados y sus sumas coincidían.

## Recuperar

Antes de restaurar, debe detenerse `red-vigilancia.service` y conservarse el estado actual. El archivo contiene las carpetas `proyecto/` y `credenciales/`, y un `manifest.json` con las sumas de los archivos. Debe revisarse su contenido antes de copiar cada carpeta a su destino; no debe extraerse directamente sobre la raíz del sistema.

No incluye el sistema operativo, el entorno virtual ni los modelos descargados. Después de reinstalar Raspberry Pi OS deben reinstalarse las dependencias. La copia completa de recuperación anterior se conserva por separado.

## Copia externa automática en Windows

El programa `scripts/copiar_copias_windows.ps1` consulta las copias disponibles por SSH y descarga los archivos nuevos mediante SCP. Compara cada archivo con la suma SHA-256 del servidor antes de guardarlo como copia completada. No elimina las copias anteriores de Windows. Las descargas incompletas no se presentan como copias correctas.

Las copias se guardan en `Documentos/Copias Raspberry`. El archivo `resultado-copias.log` indica el resultado de cada intento. Un resultado de cero copias nuevas es normal si ya estaban descargadas y coinciden con su comprobación.

Antes de activarlo, he autorizado la clave pública en la Raspberry, he iniciado el servicio `ssh-agent` de Windows y he cargado la clave protegida mediante `ssh-add`. No he guardado ninguna contraseña en el programa ni en la tarea.

Para instalar la tarea en otro Windows, desde PowerShell, en la raíz del proyecto, sustituyendo la dirección:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\activar_copias_windows.ps1 -Servidor "DIRECCION_DE_LA_RASPBERRY"
```

La tarea se llama `Red bajo vigilancia - copia externa`. Se ejecuta con los permisos normales del usuario y solo mientras su sesión está abierta. Comprueba las copias al iniciar sesión y cada hora; la primera comprobación horaria se programa cinco minutos después de instalarla. No despierta ni enciende el ordenador. Si el PC está apagado o sin acceso a la Raspberry, la copia externa espera a una ejecución posterior. Las copias de la Raspberry siguen funcionando independientemente.

Para revisar el resultado:

```powershell
Get-ScheduledTaskInfo -TaskName "Red bajo vigilancia - copia externa"
Get-Content "$env:USERPROFILE\Documents\Copias Raspberry\resultado-copias.log" -Tail 5
```

Si cambia la dirección de la Raspberry, debe actualizarse la tarea ejecutando de nuevo el instalador con la dirección correcta. El archivo del programa debe conservarse en su ubicación, ya que la tarea lo ejecuta desde esa ruta. Si el agente deja de disponer de la clave desbloqueada, debe cargarse otra vez con `ssh-add`.

## Verificador y ensayo repetible

He añadido `scripts/verificar_copia.py` para comprobar archivos, inventario e historial, y extraer únicamente en una carpeta nueva. He probado también el arranque de un panel desde una copia ficticia extraída, sin utilizar el router ni las credenciales reales. Las instrucciones y los límites están en [pruebas-automaticas.md](pruebas-automaticas.md).

He ampliado el programa de copia para incluir también los archivos PowerShell de `scripts/`. El 18 de noviembre he instalado la ampliación y el verificador en la Raspberry y he creado una nueva copia real a las 17:19 CET. He verificado sus 46 archivos, la lectura de los 17 aparatos documentados y la integridad de sus 283 registros del historial. Después he descargado esa copia a Windows y he repetido la verificación con el mismo resultado. El panel ha seguido activo durante la actualización.

## Incidencias de Laguntza IT

La versión con soporte incluye `incidencias.local.sqlite3` mediante una captura de SQLite y los archivos compilados de `web/laguntza`. La verificación también comprueba la integridad y las referencias de las notas. Las copias anteriores que no contienen incidencias siguen siendo compatibles. [Detalle de la integración](integracion-laguntza.md).
