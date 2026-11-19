"""Incidencias privadas de Laguntza IT asociadas a Red bajo vigilancia."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import unicodedata

ESTADOS = ('new', 'in_progress', 'waiting', 'resolved')
PRIORIDADES = ('low', 'medium', 'high')
CATEGORIAS = ('Acceso y cuentas', 'Aplicaciones', 'Equipos', 'Red y conexión', 'Otros')


class ConflictoIncidencia(ValueError):
    pass


class IncidenciaNoExiste(ValueError):
    pass


def fecha():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def texto(valor, nombre, minimo, maximo):
    if not isinstance(valor, str):
        raise ValueError(f'Revisa el campo {nombre}.')
    valor = valor.strip()
    if not minimo <= len(valor) <= maximo or '\x00' in valor:
        raise ValueError(f'{nombre}: utiliza entre {minimo} y {maximo} caracteres.')
    return valor


def normalizar(valor):
    return ''.join(c for c in unicodedata.normalize('NFD', valor).casefold() if not unicodedata.combining(c))


def numero(identificador):
    if not isinstance(identificador, str) or not re.fullmatch(r'INC-[0-9]{6,12}', identificador):
        raise IncidenciaNoExiste('La incidencia no existe.')
    return int(identificador[4:])


class Incidencias:
    def __init__(self, ruta):
        self.ruta = ruta
        with self.conexion() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('La versión de la base de incidencias no es compatible.')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS incidencias (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  request_id TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL,
                  title TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL,
                  priority TEXT NOT NULL, status TEXT NOT NULL,
                  device_id TEXT, device_name TEXT, context_json TEXT NOT NULL,
                  resolution TEXT NOT NULL DEFAULT '',
                  created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                  version INTEGER NOT NULL DEFAULT 1, search_text TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS actividad_incidencias (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  incidencia_id INTEGER NOT NULL REFERENCES incidencias(id),
                  fecha TEXT NOT NULL, tipo TEXT NOT NULL, detalle TEXT NOT NULL,
                  actor TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS idx_incidencias_estado ON incidencias(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_actividad_incidencia ON actividad_incidencias(incidencia_id, id);
                PRAGMA user_version=1;
            ''')
        self.ruta.chmod(0o600)

    @contextmanager
    def conexion(self):
        with closing(sqlite3.connect(self.ruta, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db

    @staticmethod
    def publico(fila):
        return {'id': f"INC-{fila['id']:06d}", 'title': fila['title'],
                'description': fila['description'], 'category': fila['category'],
                'priority': fila['priority'], 'status': fila['status'],
                'deviceId': fila['device_id'], 'deviceName': fila['device_name'],
                'context': json.loads(fila['context_json']), 'resolution': fila['resolution'],
                'createdAt': fila['created_at'], 'updatedAt': fila['updated_at'],
                'version': fila['version']}

    def detalle(self, identificador, db=None):
        if db is None:
            with self.conexion() as conexion:
                conexion.execute('BEGIN')
                return self.detalle(identificador, conexion)
        fila = db.execute('SELECT * FROM incidencias WHERE id=?', (numero(identificador),)).fetchone()
        if fila is None:
            raise IncidenciaNoExiste('La incidencia no existe.')
        resultado = self.publico(fila)
        resultado['activity'] = [dict(item) for item in db.execute(
            'SELECT id,fecha AS date,tipo AS type,detalle AS detail,actor FROM actividad_incidencias WHERE incidencia_id=? ORDER BY id DESC',
            (fila['id'],))]
        return resultado

    def listar(self, q='', estado='all', prioridad='all', pagina=1):
        if estado not in ('all', *ESTADOS) or prioridad not in ('all', *PRIORIDADES):
            raise ValueError('Filtro de incidencias no válido.')
        if type(pagina) is not int or not 1 <= pagina <= 100000:
            raise ValueError('Página no válida.')
        q = texto(q, 'búsqueda', 0, 120)
        condiciones, valores = [], []
        if q:
            condiciones.append("search_text LIKE ? ESCAPE '\\'")
            valores.append('%' + normalizar(q).replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
        for campo, valor in (('status', estado), ('priority', prioridad)):
            if valor != 'all':
                condiciones.append(campo + '=?')
                valores.append(valor)
        where = ' WHERE ' + ' AND '.join(condiciones) if condiciones else ''
        with self.conexion() as db:
            db.execute('BEGIN')
            total = db.execute('SELECT COUNT(*) FROM incidencias' + where, valores).fetchone()[0]
            filas = db.execute('SELECT * FROM incidencias' + where + ' ORDER BY updated_at DESC,id DESC LIMIT 25 OFFSET ?',
                               [*valores, (pagina - 1) * 25]).fetchall()
            metricas = db.execute("SELECT COUNT(*) AS total,COALESCE(SUM(status!='resolved'),0) AS open,COALESCE(SUM(status!='resolved' AND priority='high'),0) AS high FROM incidencias").fetchone()
        return {'tickets': [self.publico(fila) for fila in filas], 'total': total,
                'page': pagina, 'pageSize': 25, 'summary': dict(metricas)}

    def crear(self, datos, equipo=None, actor='panel'):
        if not isinstance(datos, dict):
            raise ValueError('Formulario no válido.')
        titulo = texto(datos.get('title'), 'título', 5, 120)
        descripcion = texto(datos.get('description'), 'descripción', 10, 4000)
        categoria, prioridad = datos.get('category'), datos.get('priority')
        if categoria not in CATEGORIAS or prioridad not in PRIORIDADES:
            raise ValueError('Revisa la categoría y la prioridad.')
        peticion = datos.get('requestId')
        if not isinstance(peticion, str) or not re.fullmatch(r'[a-f0-9]{32}', peticion):
            raise ValueError('Actualiza el formulario antes de crear la incidencia.')
        equipo_id = datos.get('deviceId') or None
        if equipo_id is not None and (not isinstance(equipo, dict) or equipo.get('id') != equipo_id):
            raise ValueError('El aparato ya no está disponible. Actualiza el panel.')
        # La asociación y la evidencia proceden del servidor; el cliente no impone su nombre.
        nombre = equipo.get('name') if equipo_id else None
        contexto = {key: equipo.get(key) for key in ('state', 'observedAt')} if equipo_id else {}
        canonico = json.dumps([titulo, descripcion, categoria, prioridad, equipo_id], ensure_ascii=False)
        huella = hashlib.sha256(canonico.encode()).hexdigest()
        ahora = fecha()
        with self.conexion() as db:
            db.execute('BEGIN IMMEDIATE')
            anterior = db.execute('SELECT * FROM incidencias WHERE request_id=?', (peticion,)).fetchone()
            if anterior:
                if anterior['payload_hash'] != huella:
                    raise ConflictoIncidencia('Esta solicitud ya ha creado una incidencia con otros datos. Actualiza la bandeja.')
                return self.detalle(f"INC-{anterior['id']:06d}", db)
            cursor = db.execute('''INSERT INTO incidencias(request_id,payload_hash,title,description,category,priority,status,
                device_id,device_name,context_json,created_at,updated_at,search_text)
                VALUES (?,?,?,?,?,?,'new',?,?,?,?,?,?)''',
                (peticion, huella, titulo, descripcion, categoria, prioridad, equipo_id, nombre,
                 json.dumps(contexto, ensure_ascii=False), ahora, ahora,
                 normalizar(' '.join((titulo, descripcion, categoria, nombre or '')))))
            identificador = f'INC-{cursor.lastrowid:06d}'
            db.execute('UPDATE incidencias SET search_text=search_text || ? WHERE id=?',
                       (' ' + identificador.lower(), cursor.lastrowid))
            db.execute('INSERT INTO actividad_incidencias(incidencia_id,fecha,tipo,detalle,actor) VALUES (?,?,?,?,?)',
                       (cursor.lastrowid, ahora, 'created', 'Incidencia creada manualmente.', actor))
            return self.detalle(identificador, db)

    def actualizar(self, identificador, datos, actor='panel'):
        if not isinstance(datos, dict) or type(datos.get('version')) is not int:
            raise ValueError('Actualiza el detalle antes de guardar.')
        with self.conexion() as db:
            db.execute('BEGIN IMMEDIATE')
            actual = self.detalle(identificador, db)
            if actual['version'] != datos['version']:
                raise ConflictoIncidencia('La incidencia ha cambiado en otra vista. Actualiza el detalle antes de guardar.')
            estado, prioridad = datos.get('status', actual['status']), datos.get('priority', actual['priority'])
            if estado not in ESTADOS or prioridad not in PRIORIDADES:
                raise ValueError('Estado o prioridad no válidos.')
            nota = texto(datos.get('note', ''), 'nota', 0, 2000)
            resolucion = texto(datos.get('resolution', actual['resolution']), 'resolución', 0, 4000)
            if estado == 'resolved' and len(resolucion) < 10:
                raise ValueError('Describe la solución con al menos 10 caracteres para cerrar la incidencia.')
            reabierta = actual['status'] == 'resolved' and estado != 'resolved'
            if reabierta and len(nota) < 10:
                raise ValueError('Explica el motivo de reapertura con al menos 10 caracteres.')
            if reabierta:
                resolucion = ''
            cambios = []
            if estado != actual['status']:
                cambios.append(('reopened' if reabierta else 'status', actual['status'] + ' → ' + estado))
            if prioridad != actual['priority']:
                cambios.append(('priority', actual['priority'] + ' → ' + prioridad))
            if resolucion != actual['resolution'] and resolucion:
                cambios.append(('resolution', resolucion))
            if nota:
                cambios.append(('note', nota))
            if not cambios:
                return actual
            ahora = fecha()
            db.execute('UPDATE incidencias SET status=?,priority=?,resolution=?,updated_at=?,version=version+1 WHERE id=?',
                       (estado, prioridad, resolucion, ahora, numero(identificador)))
            db.executemany('INSERT INTO actividad_incidencias(incidencia_id,fecha,tipo,detalle,actor) VALUES (?,?,?,?,?)',
                           [(numero(identificador), ahora, tipo, detalle, actor) for tipo, detalle in cambios])
            return self.detalle(identificador, db)
