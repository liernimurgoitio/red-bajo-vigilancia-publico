import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, access } from 'node:fs/promises';
import { DemoModel, sshScenario, summarizeSsh } from '../demo/model.mjs';

const now = Date.parse('2026-11-19T10:00:00Z');
test('los datos iniciales son ficticios y sus estados suman el inventario', () => {
  const model = new DemoModel(now);
  const counts = model.counts();
  assert.deepEqual(counts, { total: 8, connected: 5, disconnected: 2, unknown: 1 });
  assert.equal(counts.total, counts.connected + counts.disconnected + counts.unknown);
  for (const device of model.devices) assert.match(device.ip, /^192\.0\.2\.\d+$/);
});
test('una transición es amarilla y solo se registra al confirmar', () => {
  const model = new DemoModel(now);
  model.beginChange('impresora');
  assert.equal(model.group(model.find('impresora')), 'yellow');
  assert.equal(model.history.length, 3);
  assert.equal(model.confirmChange('impresora', now + 2000), true);
  assert.equal(model.group(model.find('impresora')), 'green');
  assert.equal(model.history.length, 4);
  assert.equal(model.history[0].type, 'conectado');
  assert.equal(model.confirmChange('impresora'), false);
  assert.equal(model.history.length, 4);
});
test('el corte de consulta no borra estados ni inventa eventos', () => {
  const model = new DemoModel(now);
  const history = structuredClone(model.history);
  const counts = model.counts();
  model.setFailure(true);
  assert.ok(model.devices.every(device => model.group(device) === 'gray'));
  assert.throws(() => model.beginChange('movil'));
  model.setFailure(false);
  assert.deepEqual(model.counts(), counts);
  assert.deepEqual(model.history, history);
});
test('no se solapan una transición y un corte', () => {
  const model = new DemoModel(now);
  model.beginChange('tablet');
  assert.throws(() => model.beginChange('movil'));
  assert.throws(() => model.setFailure(true));
  model.confirmChange('tablet');
  assert.equal(model.busy, false);
});
test('se puede editar sin alterar la identidad ni el historial anterior', () => {
  const model = new DemoModel(now);
  const history = structuredClone(model.history);
  model.edit('movil', 'Teléfono de pruebas', 'Consultar los ejemplos');
  assert.equal(model.find('movil').name, 'Teléfono de pruebas');
  assert.equal(model.filter({ search: 'telefono de PRUEBAS' })[0].id, 'movil');
  assert.deepEqual(model.history, history);
  assert.throws(() => model.edit('tablet', 'TELEFONO DE PRUEBAS', 'Otra función'));
  assert.throws(() => model.edit('tablet', '', 'Otra función'));
});
test('encendido y conexión de la TV son estados independientes', () => {
  const model = new DemoModel(now);
  const history = model.history.length;
  assert.equal(model.find('televisor').power, 'apagada');
  assert.equal(model.togglePower('televisor'), 'encendida');
  assert.equal(model.find('televisor').state, 'conectado');
  assert.equal(model.history.length, history);
  model.beginChange('televisor'); model.confirmChange('televisor');
  assert.throws(() => model.togglePower('televisor'));
});
test('restablecer descarta cambios y transiciones pendientes', () => {
  const model = new DemoModel(now);
  model.edit('movil', 'Nombre temporal', 'Función temporal');
  model.beginChange('impresora');
  model.reset(now);
  assert.equal(model.find('movil').name, 'Móvil de ejemplo');
  assert.equal(model.confirmChange('impresora'), false);
  assert.equal(model.history.length, 3);
});
test('el filtro por estado usa el estado visible y admite cero resultados', () => {
  const model = new DemoModel(now);
  model.beginChange('impresora');
  assert.deepEqual(model.filter({ state: 'yellow' }).map(device => device.id), ['impresora']);
  assert.deepEqual(model.filter({ search: 'nombre que no existe' }), []);
});
test('ARM: coincidencia parcial reproduce la muestra de tres minutos', () => {
  const summary = summarizeSsh(sshScenario('parcial', now));
  assert.equal(summary.count, 3);
  assert.equal(summary.both, 1);
  for (const rule of summary.rules) {
    assert.equal(rule.support, 1 / 3);
    assert.equal(rule.confidence, 0.5);
    assert.equal(rule.lift, 0.75);
  }
});
test('ARM: confianza del 100 % puede coexistir con lift de 1', () => {
  const summary = summarizeSsh(sshScenario('confianza', now));
  assert.equal(summary.count, 2);
  assert.deepEqual(summary.rules.map(rule => rule.confidence), [0.5, 1]);
  assert.ok(summary.rules.every(rule => rule.lift === 1));
});
test('ARM: los mensajes repetidos no crean minutos ni reglas adicionales', () => {
  const events = sshScenario('repetidos', now);
  const summary = summarizeSsh(events);
  assert.equal(events.length, 3);
  assert.equal(summary.count, 1);
  assert.equal(summary.incomplete, 1);
  assert.deepEqual(summary.rules, []);
});
test('la demo no contiene clientes de red ni direcciones del laboratorio real', async () => {
  for (const file of ['model.mjs', 'app.mjs']) {
    const source = await readFile(new URL('../demo/' + file, import.meta.url), 'utf8');
    assert.doesNotMatch(source, /\b(?:fetch|XMLHttpRequest|WebSocket|EventSource)\s*\(/);
    assert.doesNotMatch(source, /192\.168\.|100\.77\.|\/api\//);
    assert.doesNotMatch(source, /\b(?:localStorage|sessionStorage)\b/);
  }
});
test('todas las imágenes de ejemplo están disponibles localmente', async () => {
  for (const device of new DemoModel(now).devices) {
    if (device.photo) await access(new URL('../demo/photos/' + device.photo, import.meta.url));
  }
});
