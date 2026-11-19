# Incidencias con Laguntza IT

He conectado el inventario de Red bajo vigilancia con la interfaz de Laguntza IT para documentar problemas de soporte, su seguimiento y su resolución. He activado esta integración de laboratorio en la Raspberry y he publicado la demo ficticia en el portafolio. Las pruebas automáticas y las comprobaciones manuales se describen por separado.

## Comprobación de la entrega · 19 de noviembre de 2026

He completado la activación en la Raspberry. El instalador ha informado de que la interfaz, la API privada y la copia de incidencias han superado sus comprobaciones, y ha conservado los archivos anteriores para una reversión.

En el panel privado he creado una incidencia identificada expresamente como prueba, asociada a la impresora. He cambiado su estado a En curso, he añadido una nota y he comprobado que ambos datos se han conservado al refrescar. Después he cerrado la incidencia con una resolución que indica que no ha sido necesaria ninguna reparación.

He abierto la demo pública desde una ficha de aparato y he comprobado el aviso de datos ficticios y la selección del aparato en Laguntza IT. He comprobado también la ficha actualizada del portafolio, incluido el apartado «Del inventario al soporte IT». He retirado la carpeta de preparación y los archivos anteriores de la zona pública del alojamiento.

La activación y el recorrido del panel se han confirmado durante la sesión con su propietaria; no se ha realizado una nueva inspección remota de sus datos privados para esta anotación. La comprobación pública ha incluido navegación y apertura del formulario; el ensayo completo de resolución en la demo está cubierto por las pruebas de interfaz, y no se atribuye aquí a una nueva comprobación manual.

- Servidor: 29 pruebas Python correctas.
- Laguntza IT: 20 pruebas de interfaz y contrato, revisión del código y compilación correctas.
- Demo: 15 pruebas Node correctas.
- Activador: dos ensayos con archivos temporales y servicios simulados; además se ha confirmado la activación real descrita arriba.

Esta comprobación no equivale a una recuperación completa en otra Raspberry ni a la incorporación de Zaintza SOC.

## Recorrido de uso

1. En una ficha del inventario, pulsa **Crear incidencia**. También puedes abrir **Incidencias · Laguntza IT** y elegir un aparato o dejarlo sin asociar.
2. Describe lo que ocurre, las comprobaciones que has realizado y la prioridad. La creación siempre es manual: una desconexión habitual no abre incidencias automáticamente.
3. Cambia el estado a **En curso** o **Pendiente del usuario** y añade notas con el resultado de cada comprobación.
4. Para marcarla como **Resuelta**, documenta una solución de al menos diez caracteres. Para reabrirla, explica el motivo en una nota.

El nombre y el estado observado se conservan como evidencia del momento de creación. No son el estado en directo del aparato. El identificador del router puede cambiar si el aparato cambia su identidad de red; la incidencia ya creada conserva su ficha original. No se guardan IP ni MAC en la incidencia.

## Separación de entornos

| Entorno | Persistencia | Acceso |
| --- | --- | --- |
| Raspberry, `/soporte/` | `incidencias.local.sqlite3`, privado | Contraseña del panel, LAN o Tailscale |
| Demo pública, `/demo/soporte/` | Memoria de la página; se reinicia al recargar | Datos ficticios; no llama a la API privada |
| Prototipo independiente de Laguntza | Memoria de la página | Pruebas de interfaz con datos ficticios |

El código React se mantiene en [Laguntza IT](https://github.com/liernimurgoitio/laguntza-it). Este repositorio mantiene el servidor Python, las pruebas HTTP y la preparación de su compilación. No se ha incorporado todavía la detección de Zaintza SOC al flujo de incidencias.

## Preparar la interfaz

En el repositorio Laguntza IT:

```bash
cd client
npm ci
npm run lint
npm test
npm run build
```

En Red bajo vigilancia, usando las rutas de tus copias locales:

```bash
python scripts/preparar_laguntza.py --origen /ruta/laguntza-it/client/dist
```

El programa valida la compilación, copia solo archivos web a `web/laguntza` y conserva una versión anterior si existe. No copia `node_modules`, fuentes ni archivos de configuración. No necesita Node.js en la Raspberry: allí se sirve la compilación ya preparada. Los archivos compilados están excluidos de Git y se incluyen en la copia privada.

Actualiza el servidor y la interfaz juntos, con el servicio detenido y una copia verificada antes del cambio. Reinicia después `red-vigilancia.service`. Comprueba que `/soporte/` pide acceso y muestra la bandeja; no uses incidencias ficticias en el historial real. Si falla, recupera los archivos anteriores antes de reiniciar. La contraseña se introduce en la terminal del propietario, nunca en el código ni en GitHub.

## Contrato de la API

Todas las rutas requieren el mismo acceso privado que el panel. Las operaciones de escritura requieren JSON, origen permitido y `X-Panel-Token`, obtenido en el contexto de la sesión del proceso. El token cambia al reiniciar; el botón de actualización recupera el contexto.

| Método y ruta | Resultado |
| --- | --- |
| `GET /api/incidencias/contexto` | Aparatos disponibles, estado observado y token; sin direcciones de red |
| `GET /api/incidencias?q=&status=all&priority=all&page=1` | Lista de 25 elementos, total filtrado y contadores globales |
| `GET /api/incidencias/INC-000001` | Detalle y actividad |
| `POST /api/incidencias` | Alta manual con respuesta 201 |
| `POST /api/incidencias/INC-000001` | Seguimiento con la versión que se ha leído |

Alta: `requestId` (32 caracteres hexadecimales), `title` (5–120), `description` (10–4000), `category`, `priority` y `deviceId` opcional. El servidor determina el nombre y la evidencia del aparato. Repetir la misma solicitud no duplica la incidencia; reutilizar su identificador con otros datos produce 409.

Seguimiento: `version`, `status`, `priority`, `note` y `resolution`. Estados: `new`, `in_progress`, `waiting`, `resolved`. Prioridades: `low`, `medium`, `high`. La actividad se añade sin borrar las notas anteriores. Dos ediciones de la misma versión no se sobrescriben: la segunda recibe 409 y debe actualizar el detalle antes de guardar.

Errores: 400 por formulario inválido, 401 sin acceso al panel, 403 por origen o token no autorizado, 404 si no existe y 409 por conflicto. Los errores de almacenamiento devuelven un mensaje general. La interfaz conserva el formulario cuando no puede guardar y no sustituye un fallo real por datos de demo.

## Pruebas y recuperación

He comprobado el alta, reintentos, filtros, paginación, resolución, reapertura, escritura simultánea, acceso HTTP, protección de origen y persistencia tras reiniciar un servidor con router ficticio. También he generado y extraído una copia con incidencias y notas, y he comprobado su lectura después de recuperarla.

La copia captura ambas bases mediante la API de SQLite. La verificación comprueba sumas, integridad, versión de incidencias y referencias del seguimiento. Este ensayo automatizado no sustituye una recuperación completa en otra Raspberry.

## Alcance profesional y límites

El trabajo permite demostrar React, una API HTTP en Python, SQLite, validación en el servidor, pruebas de integración, despliegue con systemd y copias verificadas. Es un laboratorio para portafolio, con una identidad compartida (`panel`), sin roles, asignaciones por técnico, SLA, notificaciones ni auditoría independiente de personas. El historial de actividad no es un registro inviolable. No es un SOC ni un sistema de tickets empresarial.

La exposición pública corresponde a la demo estática. La API privada no se publica en Internet; el acceso remoto mantiene Tailscale. La autenticación HTTP del panel en la LAN tiene las mismas condiciones que el panel existente; no se ha añadido TLS local en esta fase.
