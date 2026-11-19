# Demo con datos ficticios

Esta demo reproduce las funciones principales del panel sin consultar el router, acceder a una cuenta ni controlar aparatos reales. Los nombres, direcciones, estados y eventos son ejemplos.

## Abrir localmente

Desde la raíz del repositorio:

```bash
python -m http.server 4175 --bind 127.0.0.1 --directory demo
```

Después abro `http://127.0.0.1:4175` en el navegador. No necesita instalar dependencias ni introducir contraseñas. Al terminar cierro el servidor con Ctrl+C.

## Qué permite probar

- Explorar el inventario por colores, buscar aparatos y ocultar las IP ficticias.
- Simular una conexión o desconexión y ver el cambio amarillo antes de confirmarse.
- Consultar y filtrar el historial de la demo.
- Simular un corte de consulta y su recuperación sin inventar desconexiones.
- Editar el nombre y la función de un aparato dentro de la demo.
- Simular el estado de encendido de una TV, separado de su conexión de red.
- Comparar tres muestras educativas de eventos SSH y sus asociaciones ARM.
- Descargar un CSV con los eventos ficticios del ejemplo elegido.

Las modificaciones se mantienen únicamente en la página abierta. No se guardan en el servidor ni en el almacenamiento del navegador. Al recargar o restablecer la demo se recuperan los ejemplos iniciales. El historial se limita a 500 entradas.

## Pruebas

Con Node.js disponible:

```bash
node --test tests/test_demo.mjs
```

He comprobado 13 pruebas de estados, transiciones, historial, edición, encendido de TV, filtros y cálculo ARM. También he comprobado que los programas de la demo no contienen clientes de red ni direcciones del laboratorio real y que sus imágenes están disponibles localmente.

Los enlaces de la cabecera permiten salir al portafolio y al código en GitHub. Las fotos son ilustrativas y no corresponden a datos obtenidos de una red durante la demo.

La demo no comprueba la compatibilidad con routers o televisores, los permisos de la Raspberry ni la recuperación de un servidor real. Esas pruebas están documentadas por separado en el proyecto.
