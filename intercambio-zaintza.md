# Intercambio ficticio entre Zaintza SOC y Laguntza IT

He implementado un recorrido manual y limitado a ejemplos ficticios. El código y las pruebas están preparados; esta entrega requiere una nueva publicación y una activación separada. No se ha modificado la investigación ni el registro Seguridad de ningún equipo real.

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
