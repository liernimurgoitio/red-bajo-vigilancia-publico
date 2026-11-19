# Demo con datos ficticios

Esta demo reproduce las funciones principales del panel sin consultar el router, acceder a una cuenta ni controlar aparatos reales. Los nombres, direcciones, estados y eventos son ejemplos.

[Abrir la demo pública](https://liernimurgoitio.net/demo/)

El 19 de noviembre de 2026 he publicado la demo en la ruta /demo/ del dominio del portafolio. He confirmado que la página se puede abrir sin iniciar sesión y que el botón del portafolio apunta a esa ruta. Los archivos están incluidos en public/demo dentro del código del portafolio. El cambio de acceso a público ha sido autorizado expresamente. La revisión visual automática del navegador sigue sin completarse por una limitación de la herramienta.

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

## Incidencias con Laguntza IT

Cada ficha permite abrir **Crear incidencia** con el aparato seleccionado. La sección de soporte incluye altas, notas, resolución y reapertura con datos ficticios. Los cambios se mantienen en memoria y se pierden al recargar; la página de soporte recibe solo el nombre, el identificador y el estado de ejemplo mediante la URL.

El código se mantiene en [Laguntza IT](https://github.com/liernimurgoitio/laguntza-it). Para reproducir la entrega: compila `client` con `npm ci` y `npm run build`, copia su `dist` a `demo/soporte` y añade `<meta name="laguntza-mode" content="demo-integrada" />` en la cabecera de su `index.html`. Esa marca fija el modo ficticio también cuando la demo se aloja en otra carpeta. El archivo `laguntza-build.json` registra el origen y las sumas de los archivos entregados. No copies fuentes, dependencias ni bases de datos al alojamiento público.
