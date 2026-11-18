"""Historial privado de cambios observados en la lista del router."""
import sqlite3
from contextlib import contextmanager, closing

class HistorialRed:
    def __init__(self, ruta):
        self.ruta = ruta
        self.anteriores = None
        with self.conexion() as db:
            db.execute("CREATE TABLE IF NOT EXISTS eventos (id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, equipo_id TEXT NOT NULL, alias TEXT NOT NULL, tipo TEXT NOT NULL)")
    @contextmanager
    def conexion(self):
        with closing(sqlite3.connect(self.ruta,timeout=2)) as db:
            with db:
                yield db
    def observar(self, dispositivos, fecha):
        actuales = {item["id"]:item["estado"] for item in dispositivos if item.get("estado") in ("conectado","desconectado")}
        if self.anteriores is None:
            self.anteriores = actuales
            return
        cambios = []
        for item in dispositivos:
            anterior = self.anteriores.get(item["id"])
            actual = actuales.get(item["id"])
            if anterior and actual and anterior != actual:
                cambios.append((fecha,item["id"],item["alias"],actual))
            elif anterior is None and actual == "conectado":
                cambios.append((fecha,item["id"],item["alias"],"primera_deteccion"))
        if cambios:
            with self.conexion() as db:
                db.executemany("INSERT INTO eventos(fecha,equipo_id,alias,tipo) VALUES (?,?,?,?)",cambios)
        self.anteriores.update(actuales)
    def consultar(self):
        with self.conexion() as db:
            db.row_factory = sqlite3.Row
            filas = db.execute("SELECT id,fecha,equipo_id,alias,tipo FROM eventos ORDER BY id DESC LIMIT 500").fetchall()
            total = db.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
        return {"eventos":[dict(fila) for fila in filas],"total":total,"limite":500}
