// Estado ficticio de la demo. Este módulo no realiza conexiones de red.
const iso = value => new Date(value).toISOString();
const normalized = value => String(value).normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().trim();

export class DemoModel {
  constructor(now = Date.now()) { this.reset(now); }
  reset(now = Date.now()) {
    this.online = true;
    this.devices = [
      ['router', 'Router de ejemplo', 'Router', 'Cable (LAN)', '192.0.2.1', 'conectado', 'Conectar la red de ejemplo', 'router.png'],
      ['servidor', 'Servidor del laboratorio', 'Servidor', 'Cable (LAN)', '192.0.2.20', 'conectado', 'Ejecutar el panel', null],
      ['ordenador', 'Ordenador de ejemplo', 'Ordenador', 'Wi-Fi de 5 GHz', '192.0.2.30', 'conectado', 'Uso del laboratorio', 'ordenador.png'],
      ['movil', 'Móvil de ejemplo', 'Teléfono', 'Wi-Fi de 2,4 GHz', '192.0.2.40', 'conectado', 'Consultar el panel', 'movil.png'],
      ['televisor', 'Televisor de ejemplo', 'Televisor', 'Wi-Fi de 5 GHz', '192.0.2.50', 'conectado', 'Prueba de estado independiente de la conexión', 'televisor.png'],
      ['impresora', 'Impresora de ejemplo', 'Impresora', 'Wi-Fi de 2,4 GHz', '192.0.2.60', 'desconectado', 'Imprimir documentos', 'impresora.png'],
      ['tablet', 'Tablet de ejemplo', 'Tablet', 'Wi-Fi de 5 GHz', '192.0.2.70', 'desconectado', 'Consultar el inventario', 'tablet.png'],
      ['pendiente', 'Equipo por identificar', 'Sin identificar', 'Wi-Fi', '192.0.2.80', 'sin_informacion', 'Pendiente de documentar', null],
    ].map(([id, name, type, connection, ip, state, purpose, photo]) => ({
      id, name, type, connection, ip, state, purpose, photo, pending: null,
      lastSeen: state === 'conectado' ? iso(now) : state === 'desconectado' ? iso(now - 20 * 60000) : null,
      power: id === 'televisor' ? 'apagada' : null,
    }));
    this.history = [
      { id: 3, deviceId: 'movil', name: 'Móvil de ejemplo', type: 'conectado', date: iso(now - 2 * 60000) },
      { id: 2, deviceId: 'tablet', name: 'Tablet de ejemplo', type: 'desconectado', date: iso(now - 8 * 60000) },
      { id: 1, deviceId: 'impresora', name: 'Impresora de ejemplo', type: 'desconectado', date: iso(now - 20 * 60000) },
    ];
    this.sequence = 3;
  }
  get busy() { return this.devices.some(device => device.pending); }
  find(id) {
    const device = this.devices.find(item => item.id === id);
    if (!device) throw new Error('El aparato no existe en esta demo.');
    return device;
  }
  counts() {
    return { total: this.devices.length,
      connected: this.devices.filter(d => d.state === 'conectado').length,
      disconnected: this.devices.filter(d => d.state === 'desconectado').length,
      unknown: this.devices.filter(d => d.state === 'sin_informacion').length };
  }
  group(device) {
    if (!this.online) return 'gray';
    if (device.pending) return 'yellow';
    return device.state === 'conectado' ? 'green' : device.state === 'desconectado' ? 'red' : 'gray';
  }
  beginChange(id) {
    if (!this.online || this.busy) throw new Error('Espera a que termine la simulación actual.');
    const device = this.find(id);
    if (['router', 'servidor'].includes(id)) throw new Error('Elige otro aparato para esta simulación.');
    device.pending = device.state === 'conectado' ? 'desconectado' : 'conectado';
  }
  confirmChange(id, now = Date.now()) {
    const device = this.find(id);
    if (!device.pending || !this.online) return false;
    device.state = device.pending;
    device.pending = null;
    if (device.state === 'conectado') device.lastSeen = iso(now);
    this.history.unshift({ id: ++this.sequence, deviceId: id, name: device.name, type: device.state, date: iso(now) });
    this.history = this.history.slice(0, 500);
    return true;
  }
  setFailure(failed) {
    if (failed && this.busy) throw new Error('Espera a que se confirme el cambio pendiente.');
    this.online = !failed;
  }
  edit(id, name, purpose) {
    name = String(name).trim(); purpose = String(purpose).trim();
    if (!name || name.length > 60 || !purpose || purpose.length > 160) throw new Error('Completa el nombre y la función con un texto breve.');
    if (this.devices.some(d => d.id !== id && normalized(d.name) === normalized(name))) throw new Error('Ese nombre ya corresponde a otro aparato.');
    Object.assign(this.find(id), { name, purpose });
  }
  togglePower(id) {
    const device = this.find(id);
    if (id !== 'televisor' || !this.online || device.state !== 'conectado') throw new Error('La TV de ejemplo debe estar conectada.');
    device.power = device.power === 'encendida' ? 'apagada' : 'encendida';
    return device.power;
  }
  filter({ search = '', state = 'all' } = {}) {
    return this.devices.filter(d => normalized([d.name, d.type, d.ip, d.purpose].join(' ')).includes(normalized(search))
      && (state === 'all' || this.group(d) === state));
  }
}

export function sshScenario(name = 'parcial', now = Date.now()) {
  const start = new Date(now); start.setHours(10, 0, 0, 0);
  const a = 'acceso_aceptado', b = 'conexion_sin_completar';
  const samples = {
    parcial: [[0, a], [1, b], [2, a], [2, b]],
    confianza: [[0, a], [0, b], [1, a]],
    repetidos: [[0, b], [0, b], [0, b]],
  };
  if (!samples[name]) throw new Error('Ejemplo SSH no disponible.');
  return samples[name].map(([minute, type], index) => ({
    date: iso(start.getTime() + minute * 60000 + (index + 1) * 1000), type,
  }));
}

export function summarizeSsh(events) {
  const minutes = new Map();
  for (const event of events) {
    const key = Math.floor(Date.parse(event.date) / 60000);
    if (!Number.isFinite(key) || !['acceso_aceptado', 'conexion_sin_completar'].includes(event.type)) throw new Error('Evento ficticio no válido.');
    if (!minutes.has(key)) minutes.set(key, { accepted: 0, incomplete: 0 });
    minutes.get(key)[event.type === 'acceso_aceptado' ? 'accepted' : 'incomplete']++;
  }
  const groups = [...minutes.values()];
  const accepted = groups.filter(g => g.accepted).length;
  const incomplete = groups.filter(g => g.incomplete).length;
  const both = groups.filter(g => g.accepted && g.incomplete).length;
  const count = groups.length;
  const rules = both ? [
    { from: 'Acceso aceptado', to: 'Conexión sin completar', support: both / count, confidence: both / accepted, lift: both * count / (accepted * incomplete) },
    { from: 'Conexión sin completar', to: 'Acceso aceptado', support: both / count, confidence: both / incomplete, lift: both * count / (accepted * incomplete) },
  ] : [];
  return { minutes, count, accepted, incomplete, both, rules };
}
