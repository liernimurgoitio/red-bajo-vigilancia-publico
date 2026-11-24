# Intercambio ficticio entre Zaintza SOC y Laguntza IT

He implementado un recorrido manual y limitado a ejemplos ficticios. He publicado la demo y he activado esta entrega en la Raspberry. He comprobado el recorrido manual descrito a continuación. No se ha modificado la investigación ni el registro Seguridad de ningún equipo real.

## Comprobación manual · 22 de noviembre de 2026

He confirmado la publicación de los avisos junto a los formularios en la demo de Laguntza. He repetido la importación del mismo ejemplo y he comprobado que el aviso aparece debajo de Crear incidencia, con enlace al detalle y sin duplicar la incidencia. Las versiones anteriores y la carpeta temporal se han retirado de la zona pública del alojamiento.

He activado la entrega privada en la Raspberry. El activador ha informado de que la interfaz, la API y la copia de incidencias han superado las comprobaciones. Ha conservado la incidencia anterior y sus cinco registros de seguimiento, además del programa y la base anteriores para una posible reversión.

Después he abierto el panel privado y he comprobado que la nota y la resolución anteriores siguen disponibles. He importado el ejemplo ficticio de Zaintza y he creado INC-000002. He refrescado la página, he comprobado que conserva el origen ficticio y he importado de nuevo el mismo JSON. El panel ha abierto la incidencia existente y el total ha seguido siendo de dos incidencias. He cerrado INC-000002 como Resuelta con una descripción explícita de la prueba ficticia.

He solicitado después una copia nueva. El registro de systemd del 22 de noviembre muestra el inicio a las 12:16:09 y el mensaje de copia creada y verificada a las 12:16:11, seguido de una finalización correcta del servicio.

Estas comprobaciones manuales se han confirmado durante la sesión con la propietaria mediante capturas, resultados del panel y salida de su terminal. No se ha realizado una nueva lectura remota del contenido de las incidencias para esta anotación. El archivo utilizado ha sido el ejemplo ficticio común; esta sesión no acredita una captura de eventos reales de Windows ni una recuperación completa en otra Raspberry.

Las pruebas automáticas se mantienen como evidencia separada: 42 pruebas Python del servidor, 26 de interfaz y contrato de Laguntza y 18 de Zaintza. Los siete ensayos del activador se han ejecutado también con datos temporales en el Python de la Raspberry antes de la activación real.

## Comprobación de ambas reglas · 22 y 24 de noviembre de 2026

He completado el recorrido desde la interfaz de la demo de Zaintza hasta Laguntza IT en el panel privado de la Raspberry, utilizando exclusivamente detecciones ficticias.

| Regla y evento exportado | Evidencias | Resultado en Laguntza |
| --- | --- | --- |
| ZAINTZA-AUTH-001 · DEMO-4625-1006 | 6 eventos ficticios | He abierto INC-000002, ya existente, sin duplicarla y conservando su estado Resuelta. |
| ZAINTZA-AUTH-002 · DEMO-4625-3005 | 5 eventos ficticios | He creado INC-000003 y he comprobado su conservación al refrescar. Al importar de nuevo el archivo, he abierto la misma incidencia sin añadir otra. |

Antes de completar este recorrido he reproducido un problema de selección: el detalle solo ha respondido al pulsar el identificador del evento. He corregido el comportamiento para que toda la fila permita seleccionar. He publicado la corrección y he confirmado con la propietaria que pulsar el texto de DEMO-4625-1006 actualiza el detalle correspondiente.

El 24 de noviembre he cerrado INC-000003 como Resuelta, con una resolución que identifica expresamente el ensayo como ficticio. Después he solicitado una copia nueva. La salida de systemd aportada por la propietaria muestra el inicio a las 15:19:47 y el mensaje de copia creada y verificada a las 15:19:49, seguido de una finalización correcta del servicio.

La comprobación manual se ha confirmado mediante capturas del archivo exportado, resultados del panel y salida de la terminal de la propietaria. No he realizado una nueva lectura remota del contenido privado para redactar esta anotación. El resultado acredita el intercambio manual de los dos escenarios ficticios y el control de duplicados al refrescar; no acredita una captura o transferencia de eventos reales ni una restauración completa en otra Raspberry.

## Recorrido

1. En una detección de la demo de Zaintza, pulsa **Revisar exportación ficticia** y comprueba los datos exactos.
2. Descarga el archivo JSON. La operación no crea una incidencia ni cambia la investigación.
3. En Laguntza, utiliza **Importar prueba de Zaintza**. Revisa regla, intervalo, número de fallos y referencias, y confirma que es una prueba.
4. Pulsa **Usar esta prueba en el formulario**. Revisa el título, la descripción y la prioridad antes de pulsar **Crear incidencia**.
5. Documenta el seguimiento y la resolución. La incidencia conserva el origen ficticio y las referencias, sin modificar el estado en Zaintza.

El botón de preparación sustituye el borrador del formulario por la propuesta revisable. La categoría de la prueba es Acceso y cuentas y no se asocia automáticamente con un aparato del router. En la demo se puede descargar el mismo ejemplo desde Laguntza para practicar sin instalar Zaintza.

## Contrato v1

El documento admite exclusivamente estas claves, sin campos adicionales:

```json
{
  "format": "zaintza-laguntza",
  "version": 1,
  "environment": "demo",
  "sourceInstanceId": "zaintza-demo-v1",
  "detection": {
    "id": "ZAINTZA-AUTH-001:DEMO-4625-1006",
    "ruleId": "ZAINTZA-AUTH-001",
    "firstSeen": "2026-09-15T08:00:00.000Z",
    "lastSeen": "2026-09-15T08:02:30.000Z",
    "eventCount": 6,
    "evidenceRefs": ["DEMO-4625-1001", "DEMO-4625-1002", "DEMO-4625-1003", "DEMO-4625-1004", "DEMO-4625-1005", "DEMO-4625-1006"]
  }
}
```

Solo se admiten las reglas ZAINTZA-AUTH-001 y ZAINTZA-AUTH-002. Las fechas son UTC con milisegundos y el intervalo no supera cinco minutos. Se requieren entre 5 y 100 referencias únicas del tipo DEMO-4625; la referencia de detección incluye la regla y uno de esos eventos. El tamaño máximo del archivo es 16 KiB. Las variantes reales y las versiones desconocidas se rechazan.

El ejemplo común está en `tests/fixtures/zaintza-demo-v1.json`, en `examples/zaintza-demo-v1.json` de Zaintza y en las pruebas de Laguntza. El contrato JavaScript se mantiene en Zaintza y se copia en Laguntza; la validación Python se comprueba de forma independiente con el mismo ejemplo. Las copias se revisan juntas al cambiar el formato.

## API y persistencia

`POST /api/incidencias/importar-zaintza` requiere el acceso privado del panel, el token de escritura y el origen permitido. Recibe los campos habituales de alta, `source` con el documento y `confirmDemo: true`. El servidor valida el documento de nuevo; no basta con superar la revisión del navegador.

La respuesta devuelve el detalle y `importReused`. Un alta nueva devuelve 201 y `false`. Una referencia ya existente con las mismas evidencias devuelve 200 y `true`, sin cambiar título, prioridad, notas o resolución. Una referencia reutilizada con evidencias distintas devuelve 409. El texto propuesto en una segunda importación no sobrescribe una incidencia ya existente.

La clave de origen combina entorno, instancia y referencia de detección. Se guarda con un índice único en SQLite y se comprueba en la misma transacción que el alta. La información visible se conserva en `context.source` y se añade una actividad de origen. La misma referencia permanece identificable después de reiniciar y de recuperar una copia.

## Migración y recuperación

La base de incidencias pasa de la versión 1 a la 2, añadiendo una columna de referencia y su índice. He comprobado que la migración conserva una incidencia previa. Las copias existentes de versión 1 siguen siendo verificables; las nuevas incluyen la referencia y su seguimiento.

Antes de activar esta entrega se debe conservar una copia verificada y una captura de la base de incidencias anterior con el servicio detenido. Para volver al servidor de versión 1 no basta con recuperar sus archivos: hay que recuperar también la base anterior compatible. La reversión debe conservar aparte la base de la activación fallida para poder revisar cualquier cambio que haya recibido. No se debe cambiar el número de versión de SQLite a mano.

## Comprobaciones

He probado exportación de las dos reglas, ausencia de datos de cuentas o red en el archivo, rechazo del modo real, revisión previa obligatoria, límites de tamaño, campos no admitidos, importación repetida, escrituras simultáneas, conflicto de evidencias, migración, persistencia y recuperación con seguimiento. El ensayo HTTP utiliza un router ficticio y comprueba el acceso y el token antes de importar.

La demo no llama a la API privada y reinicia los cambios al recargar. La versión privada guarda en SQLite. No se ha implementado autenticidad criptográfica del documento, correlación automática entre ventanas, sincronización entre servicios ni una integración de eventos reales. El archivo es una prueba revisable, no una acreditación de que haya ocurrido un ataque.

## Activador de la entrega privada

He preparado `scripts/activar_entrega.py` para activar una entrega local con manifiesto y archivos compilados privados. Antes de tocar el servicio, valida los archivos y solicita una copia nueva verificada. Después detiene el servicio, captura la base anterior mediante SQLite y conserva los archivos y la interfaz. Si la comprobación de arranque falla, recupera también la base compatible anterior y guarda aparte la base de la activación fallida.

El activador comprueba las sumas de los archivos servidos, lee la API con el acceso privado existente y verifica que se conservan las incidencias y el seguimiento anteriores. No crea incidencias ficticias en la base real. Genera después una copia nueva y restaura el estado previo del temporizador de copias. Si falla la copia final, informa de que el panel nuevo sigue activo y requiere revisar las copias; no revierte datos ya aceptados por el panel.

La opción `--comprobar` valida la entrega y lee la integridad y compatibilidad de la base actual sin activar cambios ni pedir sudo. La activación se ejecuta como `admin-lab`, sin anteponer sudo al programa; solo los pasos de systemd solicitan la contraseña de administración. El mensaje de activación y el recibo local son la evidencia para registrar el resultado real después de ejecutarlo.

He comprobado siete escenarios con servicios simulados y bases SQLite reales de prueba: actualización conservando datos, fallo de arranque, fallo de escritura del código, fallo de copia previa, fallo de copia final, archivo alterado y rechazo de una compilación pública con modo demo fijo. Estos ensayos no se presentan como una activación real del servidor.
