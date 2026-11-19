# Pruebas automáticas y recuperación

He preparado pruebas repetibles con datos ficticios para comprobar cambios en el código sin consultar el router doméstico ni controlar televisores reales.

## Ejecutar las pruebas

Desde la raíz del proyecto, con Python 3.11 o posterior y las dependencias del servidor instaladas:

```bash
python -m pip install -r requirements-servidor.txt
python -m unittest discover -s tests -v
```

En Windows puedo utilizar el entorno virtual:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

La prueba del panel requiere las dependencias del servidor. Sin ellas se omite esa prueba y se indica expresamente en el resultado. Las demás solo requieren la biblioteca estándar de Python.

## Qué he comprobado

He ejecutado 16 pruebas locales con resultado correcto:

- Creación, comprobación y extracción de una copia en una carpeta nueva.
- Copia del historial mientras SQLite utiliza WAL y mantiene una conexión abierta.
- Conservación de siete versiones sin eliminar archivos ajenos.
- Inclusión de los programas PowerShell de copia externa.
- Rechazo de archivos modificados, rutas fuera del destino, enlaces y nombres repetidos.
- Rechazo de un historial que no se puede leer como una base SQLite del proyecto.
- Protección de una carpeta de destino que ya existe.
- Ausencia de desconexiones inventadas cuando faltan observaciones o se reinicia el historial.
- Resultados ARM de la muestra controlada, agrupación sin duplicados y límite final exclusivo.
- Arranque de un panel desde una copia ficticia extraída, con inventario e historial recuperados.
- Petición de contraseña en el panel de prueba y rechazo de cambios sin token o desde otro origen.
- Recuperación tras un corte de consulta simulado y conservación del historial después de reiniciar el servidor de prueba.

La prueba de integración recupera el código desde el archivo de copia, lo inicia en un proceso separado y sirve HTTP solo en loopback, en un puerto temporal. El router es ficticio y el proceso bloquea las conexiones salientes a otras direcciones. No modifica el servicio de la Raspberry ni utiliza sus credenciales.

## Ejecución en GitHub

El archivo `.github/workflows/pruebas.yml` prepara estas comprobaciones para Linux y Windows, con Python 3.11 y 3.13, al subir cambios a `main` o abrir una solicitud de cambios. También permite iniciarlas manualmente desde Actions. No necesita secretos del laboratorio.

El 18 de noviembre de 2026 he comprobado también una ejecución de GitHub Actions en el repositorio de trabajo: las cuatro combinaciones de sistema y versión de Python han terminado correctamente. Cada una ha ejecutado las 16 pruebas, incluida la del panel recuperado. El resultado de una ejecución no sustituye al de los cambios posteriores ni a una prueba en hardware ARM. Una instalación limpia de Raspberry Pi OS todavía requiere una comprobación real de restauración y arranque.

## Verificar una copia real

He añadido `scripts/verificar_copia.py` para repetir las comprobaciones sin pegar código manualmente. No necesita instalar dependencias adicionales.

```bash
python3 scripts/verificar_copia.py /ruta/a/la/copia.tar.gz
```

El programa compara los archivos con el manifiesto, comprueba la lectura del inventario y verifica la integridad de SQLite cuando la copia incluye el historial. Solo muestra cantidades y resultados, no contraseñas. He comprobado una copia real conservada en Windows: 43 archivos verificados, 17 aparatos documentados y 237 registros del historial. Son datos de esa copia anterior, no el estado actual del panel. Después de instalar el verificador y la ampliación de las copias en la Raspberry, he creado otra copia real a las 17:19 CET del 18 de noviembre: he verificado 46 archivos, 17 aparatos documentados y 283 registros, tanto en la Raspberry como en Windows.

Para extraer después de comprobar, debo elegir una carpeta que no exista:

```bash
python3 scripts/verificar_copia.py /ruta/a/la/copia.tar.gz --extraer ~/recuperacion-nueva
```

Nunca debo indicar como destino la carpeta del panel activo. El programa rechaza destinos existentes, enlaces y rutas que salgan de la carpeta de extracción. En Linux crea carpetas privadas y archivos con permisos restringidos. En Windows se aplican además los permisos de acceso de la carpeta del usuario.

Una suma SHA-256 ayuda a detectar cambios, pero un manifiesto guardado dentro del mismo archivo no demuestra quién ha creado la copia. Debo utilizar copias propias conservadas en ubicaciones de confianza. Esta comprobación no inicia el panel ni prueba que el sistema operativo o las dependencias estén instalados.


## Pruebas de la demo

He añadido 13 pruebas en JavaScript para los datos ficticios y las simulaciones de la demo. Se ejecutan con `node --test tests/test_demo.mjs`, además de las 16 pruebas de Python. El flujo de GitHub Actions incluye ambas comprobaciones. Los resultados locales de la demo han sido correctos; la revisión visual del navegador no se ha completado por una limitación de la herramienta de control.
