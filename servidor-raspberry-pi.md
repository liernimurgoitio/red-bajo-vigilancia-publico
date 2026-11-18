# Servidor doméstico en Raspberry Pi

Esta fase forma parte de **Red bajo vigilancia**. He trasladado el panel desde Windows a una Raspberry Pi para mantener la vigilancia sin depender de una sesión abierta en el PC.

**Estado a 18 de noviembre de 2026:** he comprobado la consulta del router, el historial, el funcionamiento como servicio y el arranque automático después de reinstalar y recuperar los datos. He verificado el acceso desde Android con datos móviles mediante Tailscale y el funcionamiento con el PC apagado. También he comprobado las copias diarias, la lectura de los datos extraídos y la descarga automática a Windows después de reiniciar el ordenador.

## Entorno

| Elemento | Configuración |
| --- | --- |
| Equipo | Raspberry Pi 3B+ |
| Sistema | Raspberry Pi OS Lite (64-bit), basado en Debian GNU/Linux 13 «trixie» |
| Arquitectura comprobada | `aarch64` |
| Python comprobado | 3.13.5 |
| Almacenamiento | MicroSD de 16 GB |
| Nombre del equipo | `red-vigilancia` |
| Usuario de administración | `admin-lab` |
| Conexión actual documentada | Cable de red al router |
| Hora | `Europe/Madrid`, con sincronización NTP comprobada |
| Acceso privado exterior | Tailscale en Raspberry y Android |

La Raspberry pertenece a la red doméstica. El [laboratorio Ubuntu](laboratorio-ssh.md) sigue siendo un entorno separado con red Host-only.

## Instalación y primera conexión

He preparado la microSD desde Windows con Raspberry Pi Imager 2.0.12. He seleccionado Raspberry Pi 3 y Raspberry Pi OS Lite de 64 bits. He personalizado el nombre del equipo, la localización, el usuario, el Wi-Fi y SSH; he dejado Raspberry Pi Connect desactivado.

He esperado a que Imager terminara la escritura y verificación. Después he iniciado el sistema y he conectado por SSH desde Windows. He comprobado el nombre del equipo, el sistema, la arquitectura, la hora y la sincronización del reloj.

He actualizado los paquetes, he comprobado un reinicio y he consultado los servicios fallidos. En la primera instalación también he creado una clave Ed25519 dedicada y he probado su acceso desde una conexión nueva. Después de reinstalar he utilizado inicialmente acceso por contraseña. El 18 de noviembre he vuelto a autorizar la clave pública, he comprobado el acceso con la clave protegida por su frase y he utilizado el agente SSH de Windows para permitir las copias sin preguntas interactivas. He comprobado que este acceso sigue funcionando en la tarea después de reiniciar Windows.

## Traslado del proyecto

He preparado un entorno virtual y he instalado el cliente Sagemcom, el cliente webOS y Aiohttp. He copiado por SCP el panel, los programas, el inventario privado, las fotos y el historial.

He abierto el panel desde la red doméstica y he comprobado una desconexión y una reconexión controladas. Las nuevas entradas han aparecido en el historial persistente.

He corregido una regla heredada de Windows que asociaba «Mi PC» al equipo donde se ejecutaba el servidor. La identificación ahora da prioridad a la MAC guardada, después al identificador del router y finalmente a la IP configurada. He identificado la Raspberry con una ficha propia desde el panel.

## Arranque automático

He preparado las credenciales en la Raspberry con:

```bash
.venv/bin/python scripts/preparar_servicio.py
```

Este asistente guarda el usuario del router, su contraseña y la contraseña del panel en `~/.config/red-vigilancia/`. La carpeta tiene permisos `700` y los archivos `600`. No los he añadido al repositorio.

La unidad `red-vigilancia.service` ejecuta el programa como `admin-lab`, sin preguntas interactivas, y carga las credenciales mediante `LoadCredential`. Incluye reinicio del proceso ante fallos y limitaciones del entorno de ejecución. He comprobado la recuperación del proceso ante una terminación controlada y la reanudación de consultas tras un corte de red. Estas pruebas no cubren todos los fallos posibles, como una contraseña del router cambiada o un cambio de dirección del servidor.

Después de instalar la unidad:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now red-vigilancia.service
systemctl status red-vigilancia.service --no-pager -l
```

He comprobado `active (running)`, he cerrado SSH y he confirmado que la última comprobación del panel seguía avanzando. Después de recuperar el sistema, he repetido el reinicio y he confirmado que el panel ha vuelto a funcionar.

## Recuperación después de un fallo del programa

El 18 de noviembre de 2026 he provocado una terminación controlada del programa del panel, manteniendo encendida la Raspberry:

```bash
sudo systemctl kill -s SIGKILL red-vigilancia.service
```

He consultado el registro con:

```bash
sudo journalctl -u red-vigilancia.service -n 15 --no-pager
```

El registro ha mostrado esta secuencia:

| Hora CET | Resultado observado |
| --- | --- |
| 15:10:41 | El proceso ha terminado por la señal enviada |
| 15:10:51 | systemd ha iniciado de nuevo el servicio |
| 15:10:53 | El programa ha vuelto a consultar el router |

He actualizado el panel y he comprobado que los aparatos y el historial seguían visibles. El historial ha mostrado 273 cambios guardados después del reinicio. Esta prueba confirma la recuperación del proceso ante esta terminación; no demuestra todavía la recuperación ante cortes de red o daños en la tarjeta.

## Recuperación después de un corte de red

El 18 de noviembre de 2026 he comprobado las rutas de la Raspberry: tenía cable y Wi-Fi activos. He desconectado temporalmente el Wi-Fi y después el cable de red, manteniendo encendidos el servidor y el router. Así he evitado que la segunda conexión ocultara el corte.

El registro del mismo proceso ha mostrado un `TimeoutError` a las 15:16:42 CET y varias consultas con `ConnectionError`. Después de reconectar el cable, la consulta ha vuelto a funcionar a las 15:17:33 y ha continuado en los minutos siguientes, sin reiniciar manualmente el servicio. He abierto el panel y he comprobado que funcionaba. Al terminar he vuelto a conectar el Wi-Fi.

Esta prueba confirma la recuperación en ese corte controlado. No he probado todavía un cambio de dirección de la Raspberry, una sesión del router caducada durante un corte largo ni una pérdida de alimentación.

## Corrupción de la microSD y recuperación

He perdido el acceso por nombre y por la última IP conocida. La prueba posterior por HDMI tampoco ha mostrado imagen. He probado otra tarjeta que contenía Kodi y el equipo ha arrancado; esto ha apuntado a la tarjeta original o a su instalación, sin demostrar un daño físico.

Antes de reparar, he creado una imagen completa de la tarjeta original de **15.986.589.696 bytes**. He calculado SHA-256 durante la copia y lo he comparado con una nueva lectura del archivo guardado: ambas huellas han coincidido. La copia ha terminado sin errores de lectura. Esto verifica los datos copiados, no la integridad lógica de su sistema de archivos.

He utilizado Ubuntu en VMware para comprobar las particiones desmontadas. La revisión de EXT4 ha detectado directorios dañados, entre ellos el punto de montaje `/boot/firmware`. He aplicado reparaciones supervisadas; algunos elementos se han recuperado en `/lost+found`. La comprobación posterior de la estructura ha terminado sin errores detectados.

La revisión de `bootfs` también ha mostrado corrupción. Tras dos pasadas de reparación, la comprobación de FAT ha terminado sin errores detectados. Los archivos básicos de arranque han seguido presentes, pero la Raspberry no ha recuperado el arranque. Una estructura de archivos corregida no implica que el contenido de todos los archivos esté intacto.

He montado la partición Linux en solo lectura y he creado una segunda copia con el proyecto, las credenciales y la unidad de servicio. He comprobado que el archivo comprimido se podía leer, que el JSON privado era válido y que SQLite no presentaba errores en `PRAGMA integrity_check`.

Con las copias verificadas he reinstalado en la misma microSD. He comprobado el arranque, la conexión SSH, las actualizaciones y el reinicio antes de restaurar. Después he restaurado los datos, he recreado el entorno virtual y he activado el servicio. El panel y su arranque automático han vuelto a funcionar.

Más tarde, al instalar Tailscale, APT ha encontrado una lista de paquetes ilegible. He apartado ese índice y lo he vuelto a descargar; `apt update` ha terminado correctamente. El registro consultado ha mostrado un aviso al activar el modo de alta velocidad de la tarjeta, sin errores de E/S o de EXT4 en esa salida. La causa de la corrupción no está demostrada y sigue siendo un riesgo pendiente de seguimiento.

Las imágenes de disco y los archivos de recuperación contienen datos privados y permanecen fuera del repositorio.

## Fotos en el servidor ligero

He mantenido las imágenes transparentes y las fichas editables desde la Raspberry. El recorte que utilizaba el PC no estaba instalado en este servidor y bloqueaba el guardado de fotos nuevas; he corregido esa dependencia para permitir guardar la imagen sin procesarla.

Después he preparado una alternativa pequeña con U²-NetP y ONNX Runtime. Se ejecuta en un proceso separado, con un solo trabajo cada vez, un hilo de inferencia y un tiempo máximo de espera. El modelo se descarga durante la preparación, se verifica y se utiliza localmente; las fotos no se envían a un proveedor externo.

He comprobado el motor con pruebas locales y he preparado el modelo en la Raspberry. Queda pendiente documentar el resultado y el consumo con una fotografía real procesada desde el panel de la Raspberry. La precisión depende de la foto y del contraste del fondo.

## Estado y controles de la LG

He vinculado la LG webOS con autorización desde la TV. He comprobado que comunica `Active` cuando está encendida y que deja de responder al ponerla en espera. El panel conserva dos indicadores separados: conexión de red y encendido confirmado por la TV. La ausencia de respuesta se muestra como «TV sin confirmar».

He añadido y he probado los botones de encender y apagar en la LG vinculada. El encendido envía una señal Wake-on-LAN y el apagado utiliza webOS. La TD Systems conserva únicamente su seguimiento de red; no he configurado controles para ella.

## Acceso privado desde Android

He instalado Tailscale en la Raspberry desde su fuente oficial y la he autorizado. He instalado la aplicación en Android y he utilizado la misma cuenta.

He preparado el acceso con:

```bash
.venv/bin/python scripts/preparar_acceso_remoto.py
sudo systemctl restart red-vigilancia.service
```

El asistente guarda la dirección concreta del equipo en `tailscale.local.json`, excluido de Git. El servidor abre una segunda entrada en esa dirección, conserva la contraseña del panel y mantiene la entrada doméstica. Si la interfaz de Tailscale aún no está disponible al arrancar, reintenta abrir esa entrada.

El 17 de noviembre de 2026 he abierto el panel desde Android con el Wi-Fi desactivado y datos móviles, mediante Tailscale. Después he apagado el PC de Windows y he comprobado que el panel seguía funcionando. La Raspberry y el router han permanecido encendidos. No he abierto puertos del router ni he activado Tailscale Funnel.

## Resultados y comprobaciones pendientes

| Comprobación | Resultado |
| --- | --- |
| Sistema Lite ARM64 y reloj sincronizado | Comprobado |
| Panel, fotos y cambios de conexión desde Raspberry | Comprobado |
| Historial recuperado y SQLite íntegro en la copia | Comprobado |
| Servicio activo con SSH cerrado | Comprobado |
| Reinicio y recuperación del panel tras restaurar | Comprobado |
| Reinicio automático tras terminar el proceso | Comprobado el 18/11/2026: reinicio en 10 segundos e historial visible |
| Encendido y apagado de la LG desde el panel | Comprobado |
| Panel abierto desde Android mediante Tailscale | Comprobado |
| Prueba con datos móviles y funcionamiento con PC apagado | Comprobado el 17/11/2026 |
| SSH con clave después de reinstalar | Comprobado el 18/11/2026 |
| Recorte de una foto real y consumo en la Raspberry | Pendiente de documentar |
| Copia manual y temporizador diario | Copia creada y verificada; temporizador activado el 17/11/2026 |
| Copia fuera de la microSD | Descarga automática a Windows comprobada, también después de reiniciar el PC |
| Nuevo verificador y copia ampliada | Instalados y comprobados en la Raspberry el 18/11/2026 |
| Primera ejecución automática | Comprobada el 18/11/2026 a las 03:08 CET |
| Extracción y lectura de la copia en carpeta de prueba | Sumas correctas, inventario legible y SQLite íntegro |
| Arranque de un servidor desde una copia ficticia | Comprobado localmente con un router simulado |
| Restauración de la copia real en otra instalación de Raspberry Pi OS | Pendiente |
| Recuperación tras corte controlado de red | Comprobada el 18/11/2026; consultas reanudadas sin reiniciar el servicio |
| Causa de la corrupción de la tarjeta | No demostrada |

## Copias privadas

He preparado el programa y el temporizador para conservar siete copias diarias del inventario, las fotos, el historial y las credenciales. He comprobado la copia con una base SQLite en uso y la rotación con datos de prueba. Las instrucciones de activación y sus límites están en [Copias privadas del servidor](copias-seguridad.md). El 17 de noviembre de 2026 he creado y verificado la primera copia en la Raspberry y he activado el temporizador diario. He comprobado que la siguiente ejecución ha quedado programada y he transferido la copia a Windows. El 18 de noviembre he comprobado que la copia automática de las 03:08 CET se ha creado y verificado correctamente. Además, he extraído la copia manual en una carpeta privada de prueba y he comprobado las sumas SHA-256, la lectura del inventario y la integridad del historial. No he sustituido los datos del panel. Además, he automatizado el arranque y reinicio de un servidor separado desde una copia con datos ficticios. La restauración de la copia real sobre otra instalación de Raspberry Pi OS sigue pendiente. Las comprobaciones repetibles están descritas en [pruebas-automaticas.md](pruebas-automaticas.md).

## Referencias

- [Instalación y primer arranque de Raspberry Pi](https://www.raspberrypi.com/documentation/computers/getting-started.html).
- [Credenciales y entorno de ejecución de systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html).
- [Conexión con otros dispositivos mediante Tailscale](https://tailscale.com/docs/how-to/connect-to-devices).
- [Modelo ligero U²-NetP utilizado por Rembg](https://github.com/danielgatis/rembg/blob/v2.0.67/rembg/sessions/u2netp.py).
