# Integración de Zaintza SOC y Laguntza IT: estado y próximos pasos

## Punto de partida revisado

He revisado el lector de eventos de Windows, las dos reglas de Zaintza SOC y su editor de investigación. Zaintza obtiene eventos 4625 mediante PowerShell, agrupa fallos y conserva estados y notas en su servicio local. Laguntza IT ya permite documentar incidencias en la Raspberry. He implementado una primera conexión manual con exportaciones ficticias v1, probada con datos de ejemplo. He publicado la demo y he activado la entrega privada en la Raspberry. El 22 de noviembre de 2026 he comprobado manualmente importación, conservación al refrescar, control de duplicados, resolución y copia de seguridad con el ejemplo ficticio común.

| Proyecto | Responsabilidad actual |
| --- | --- |
| Red bajo vigilancia | Inventario, estado informado por el router e historial de conexiones |
| Zaintza SOC | Detecciones e investigación de fallos de autenticación de Windows |
| Laguntza IT | Incidencia de soporte, seguimiento y resolución |

Una detección y una incidencia tienen estados y propósitos distintos. Resolver una incidencia de soporte no debe cerrar automáticamente una investigación de seguridad.

## Primera integración comprobada

El recorrido es manual y verificable: abrir una detección en Zaintza, revisar sus evidencias y preparar una exportación para Laguntza. Antes de confirmar el alta se mostrará qué información se va a incorporar. La creación no se disparará por cada evento de Windows ni por una desconexión del inventario.

La propuesta inicial utiliza un archivo JSON de intercambio para no exponer el servicio local de Windows ni guardar contraseñas del panel en el navegador. He implementado el contrato, el exportador ficticio y la vista de revisión. El panel actualizado acepta estos archivos; las instalaciones anteriores requieren actualizar el servidor y la interfaz juntos. [Contrato, pruebas y límites](intercambio-zaintza.md).

## Datos mínimos que debe contemplar el contrato

- Versión del formato y origen, con separación explícita entre demo y datos reales.
- Identificador local de la instalación de Zaintza, regla y referencia estable de la detección.
- Fechas inicial y final, número de eventos y referencias de las evidencias.
- Resumen revisable, categoría propuesta y prioridad que el usuario debe confirmar.
- Referencia de origen conservada en la incidencia para evitar importar la misma detección dos veces.

Las cuentas, equipos y direcciones de red no se trasladarán automáticamente. La primera versión mostrará un resumen sin esos campos, y permitirá revisar el texto libre antes de guardarlo. No se utilizarán parámetros de URL para transportar evidencias reales. La lista de aparatos del router no permite asociar por sí sola una cuenta o un equipo de Windows con una ficha: esa relación requerirá confirmación.

## Criterios de aceptación antes de publicar

1. Importar una detección ficticia y revisar el resumen antes de crear la incidencia.
2. Rechazar archivos inválidos, demasiado grandes o con versión desconocida sin modificar datos.
3. Repetir una importación sin duplicar la incidencia y conservar su referencia de origen al reiniciar.
4. Añadir seguimiento y resolución sin modificar el estado de investigación en Zaintza.
5. Mantener el acceso privado, el token de escritura y la validación del servidor.
6. Incluir la referencia y las notas en las copias y comprobar su recuperación.
7. Publicar una demo que solo utilice ejemplos ficticios y documentar las limitaciones.

## Orden de trabajo

He preparado el contrato, un caso ficticio común, el exportador de Zaintza, la vista de revisión de Laguntza y la validación del servidor. He comprobado el flujo en pruebas antes de modificar el servicio activo. La publicación y la comprobación manual del importador ya están completadas. He completado también la exportación desde la interfaz de Zaintza y su importación en Laguntza con las dos reglas ficticias: AUTH-001 con seis eventos y AUTH-002 con cinco. He comprobado la conservación al refrescar, la ausencia de duplicados y la resolución, seguida de una copia verificada el 24 de noviembre de 2026 a las 15:19:49. La transferencia de eventos reales requiere una fase de diseño y comprobación independiente. La conexión automática entre servicios queda fuera de esta primera fase.

Para el portafolio se presenta como un intercambio manual con datos ficticios, desplegado y comprobado. La integración de eventos reales sigue pendiente. Las detecciones seguirán describiéndose como indicios que requieren investigación, sin afirmar que confirman un ataque.
