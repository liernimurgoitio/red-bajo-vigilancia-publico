import { DemoModel, sshScenario, summarizeSsh } from './model.mjs';

const model = new DemoModel();
const $ = selector => document.querySelector(selector);
const format = new Intl.DateTimeFormat('es-ES', { dateStyle: 'short', timeStyle: 'medium' });
const minuteFormat = new Intl.DateTimeFormat('es-ES', { hour: '2-digit', minute: '2-digit' });
const percent = new Intl.NumberFormat('es-ES', { style: 'percent', minimumFractionDigits: 1 });
const decimal = new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const views = ['visual', 'summary', 'history', 'ssh'];
const timers = new Set();
let editingId = null;
let sshEvents = sshScenario();

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function schedule(callback, delay) {
  const timer = setTimeout(() => { timers.delete(timer); callback(); }, delay);
  timers.add(timer);
}
function announce(message) { $('#simulation-message').textContent = message; }
function icon(type = 'aparato') {
  const paths = type === 'Servidor'
    ? '<rect x="17" y="8" width="30" height="48" rx="5"/><path d="M24 21h16M24 32h16M25 45h1m9 0h1"/>'
    : '<rect x="10" y="14" width="44" height="31" rx="4"/><path d="M32 45v9m-12 0h24"/>';
  const wrapper = element('span');
  wrapper.innerHTML = `<svg viewBox="0 0 64 64" fill="none" stroke="currentColor" stroke-width="3" aria-hidden="true">${paths}</svg>`;
  return wrapper.firstChild;
}
function lamp(text, color) {
  const node = element('span', undefined, 'lamp state-' + color);
  const bulb = element('span');
  bulb.innerHTML = '<svg viewBox="0 0 20 28" fill="currentColor" aria-hidden="true"><path d="M10 1a8 8 0 0 0-6 13c2 2 2 4 2 5h8c0-1 0-3 2-5A8 8 0 0 0 10 1Z"/><path d="M6 21h8v2H6zm2 4h4v2H8z"/></svg>';
  node.append(bulb.firstChild, document.createTextNode(text));
  return node;
}
function deviceLamp(device) {
  const color = model.group(device);
  const label = !model.online ? 'Sin información actual'
    : device.pending ? device.pending === 'conectado' ? 'Conexión por confirmar' : 'Desconexión por confirmar'
    : device.state === 'conectado' ? 'Conectado' : device.state === 'desconectado' ? 'Desconectado' : 'Sin información';
  return lamp(label, color);
}
function editButton(device, short = false) {
  const button = element('button', short ? 'Editar' : 'Editar ejemplo');
  button.type = 'button';
  button.setAttribute('aria-label', 'Editar ' + device.name);
  button.addEventListener('click', () => {
    editingId = device.id;
    $('#edit-name').value = device.name;
    $('#edit-purpose').value = device.purpose;
    $('#edit-error').textContent = '';
    $('#edit-dialog').showModal();
    $('#edit-name').focus();
  });
  return button;
}
function card(device) {
  const tile = element('article', undefined, 'tile');
  const picture = element('div', undefined, 'picture');
  if (device.photo) {
    const image = document.createElement('img');
    image.src = new URL('photos/' + device.photo, import.meta.url).href;
    image.alt = 'Imagen ilustrativa de ' + device.type.toLowerCase();
    image.width = 120; image.height = 120; image.loading = 'lazy';
    picture.append(image);
  } else picture.append(icon(device.type));
  const lamps = element('div', undefined, 'lamps');
  lamps.append(deviceLamp(device));
  if (device.power) {
    const available = model.online && device.state === 'conectado' && !device.pending;
    lamps.append(lamp(available ? device.power === 'encendida' ? 'TV encendida' : 'TV apagada' : 'TV sin confirmar',
      available ? device.power === 'encendida' ? 'green' : 'red' : 'gray'));
  }
  tile.append(picture, lamps, element('h3', device.name), element('p', device.type + ' · ' + device.connection, 'meta'));
  if ($('#show-ips').checked) tile.append(element('p', 'IP ficticia', 'help'), element('p', device.ip, 'ip'));
  tile.append(element('p', device.lastSeen ? 'Última detección del ejemplo: ' + format.format(new Date(device.lastSeen)) : 'Sin detección en el ejemplo', 'seen'));
  const actions = element('div', undefined, 'tile-actions');
  actions.append(editButton(device));
  if (device.power) {
    const button = element('button', device.power === 'encendida' ? 'Simular apagado de TV' : 'Simular encendido de TV');
    button.type = 'button';
    button.disabled = !model.online || model.busy || device.state !== 'conectado';
    button.addEventListener('click', () => {
      try {
        const power = model.togglePower(device.id);
        renderAll(); announce('La TV de ejemplo ahora aparece ' + power + '. Su conexión de red no ha cambiado.');
      } catch (error) { announce(error.message); }
    });
    actions.append(button);
  }
  tile.append(actions);
  return tile;
}
function renderVisual() {
  const devices = model.filter({ search: $('#visual-search').value, state: $('#visual-state').value });
  $('#visual-count').textContent = `${devices.length} de ${model.devices.length} aparatos ficticios visibles.`;
  const container = $('#device-groups'); container.replaceChildren();
  for (const [color, title] of [['green', 'Conectados'], ['yellow', 'Cambios por confirmar'], ['red', 'Desconectados'], ['gray', 'Sin información']]) {
    const selected = devices.filter(device => model.group(device) === color);
    const section = element('section', undefined, 'group group-' + color);
    const heading = element('h2');
    heading.append(element('span', '●', 'dot'), document.createTextNode(title), element('span', String(selected.length), 'count'));
    const body = element('div', undefined, 'group-content');
    if (selected.length) for (const device of selected) body.append(card(device));
    else body.append(element('p', 'Sin aparatos en este grupo con los filtros actuales.', 'help empty'));
    section.append(heading, body); container.append(section);
  }
}
function renderSummary() {
  const body = $('#summary-rows'); body.replaceChildren();
  for (const device of model.devices) {
    const row = element('tr');
    row.append(element('td', device.name), element('td', device.type + ' · ' + device.connection), element('td', device.ip));
    const state = element('td'); state.append(deviceLamp(device));
    const edit = element('td'); edit.append(editButton(device, true));
    row.append(state, element('td', device.purpose), edit); body.append(row);
  }
}
function renderHistory() {
  const search = $('#history-search').value.toLocaleLowerCase('es').trim();
  const type = $('#history-type').value;
  const events = model.history.filter(event => event.name.toLocaleLowerCase('es').includes(search) && (type === 'all' || event.type === type));
  const body = $('#history-rows'); body.replaceChildren();
  for (const event of events) {
    const row = element('tr');
    row.append(element('td', format.format(new Date(event.date))), element('td', event.name),
      element('td', event.type === 'conectado' ? 'Conectado' : 'Desconectado', event.type === 'conectado' ? 'green' : 'red'));
    body.append(row);
  }
  $('#history-count').textContent = `${events.length} cambios visibles de ${model.history.length} guardados en esta demo. El restablecimiento recupera los tres ejemplos iniciales.`;
}
function renderAll() {
  const counts = model.counts();
  for (const key of ['total', 'connected', 'disconnected', 'unknown']) $('#count-' + key).textContent = counts[key];
  const selected = $('#simulate-device').value;
  $('#simulate-device').replaceChildren();
  for (const device of model.devices.filter(d => !['router', 'servidor'].includes(d.id))) {
    const option = element('option', device.name); option.value = device.id; $('#simulate-device').append(option);
  }
  $('#simulate-device').value = model.devices.some(d => d.id === selected) && !['router', 'servidor'].includes(selected) ? selected : 'impresora';
  const disabled = !model.online || model.busy;
  $('#simulate-change').disabled = disabled;
  $('#simulate-error').disabled = disabled;
  $('#simulate-device').disabled = disabled;
  $('#connection-notice').hidden = model.online;
  $('#connection-notice').textContent = 'Consulta fallida simulada. Las bombillas quedan sin información actual y los contadores conservan el último estado confirmado. En unos segundos se recuperará el ejemplo.';
  renderVisual(); renderSummary(); renderHistory();
}

$('#simulate-change').addEventListener('click', () => {
  const id = $('#simulate-device').value;
  try {
    model.beginChange(id);
    const name = model.find(id).name;
    renderAll(); announce('Cambio simulado en ' + name + ': la bombilla amarilla espera una segunda lectura ficticia.');
    schedule(() => {
      if (model.confirmChange(id)) { renderAll(); announce('Cambio confirmado en ' + model.find(id).name + '. Se ha añadido al historial de la demo.'); }
    }, 2200);
  } catch (error) { announce(error.message); }
});
$('#simulate-error').addEventListener('click', () => {
  try {
    model.setFailure(true); renderAll(); announce('Corte de consulta simulado. No se añaden desconexiones al historial.');
    schedule(() => { model.setFailure(false); renderAll(); announce('Consulta ficticia recuperada. El inventario y el historial se han conservado.'); }, 4500);
  } catch (error) { announce(error.message); }
});
$('#reset').addEventListener('click', () => {
  for (const timer of timers) clearTimeout(timer);
  timers.clear(); model.reset();
  $('#visual-search').value = ''; $('#visual-state').value = 'all'; $('#show-ips').checked = true;
  $('#history-search').value = ''; $('#history-type').value = 'all'; $('#ssh-scenario').value = 'parcial';
  if ($('#edit-dialog').open) $('#edit-dialog').close();
  sshEvents = sshScenario(); renderAll(); renderSsh(); announce('Demo restablecida. Los cambios anteriores se han descartado.');
});
$('#edit-cancel').addEventListener('click', () => $('#edit-dialog').close());
$('#edit-form').addEventListener('submit', event => {
  event.preventDefault();
  try {
    model.edit(editingId, $('#edit-name').value, $('#edit-purpose').value);
    $('#edit-dialog').close(); renderAll(); announce('Nombre y función actualizados solo en esta demo.');
  } catch (error) { $('#edit-error').textContent = error.message; }
});
for (const id of ['visual-search', 'visual-state', 'show-ips']) $('#' + id).addEventListener('input', renderVisual);
for (const id of ['history-search', 'history-type']) $('#' + id).addEventListener('input', renderHistory);

function selectView(name, remember = true) {
  if (!views.includes(name)) name = 'visual';
  for (const view of views) {
    $('#tab-' + view).setAttribute('aria-selected', String(name === view));
    $('#tab-' + view).tabIndex = name === view ? 0 : -1;
    $('#view-' + view).hidden = name !== view;
  }
  if (remember) history.replaceState(null, '', '#' + name);
}
for (const view of views) {
  const tab = $('#tab-' + view);
  tab.addEventListener('click', () => selectView(view));
  tab.addEventListener('keydown', event => {
    const index = views.indexOf(view);
    const next = event.key === 'ArrowRight' ? views[(index + 1) % views.length]
      : event.key === 'ArrowLeft' ? views[(index - 1 + views.length) % views.length]
      : event.key === 'Home' ? views[0] : event.key === 'End' ? views.at(-1) : null;
    if (next) { event.preventDefault(); selectView(next); $('#tab-' + next).focus(); }
  });
}
window.addEventListener('hashchange', () => selectView(location.hash.slice(1), false));

function svgElement(tag, attrs = {}, text) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
function renderSsh() {
  const summary = summarizeSsh(sshEvents);
  $('#ssh-total').textContent = sshEvents.length;
  $('#ssh-accepted').textContent = sshEvents.filter(e => e.type === 'acceso_aceptado').length;
  $('#ssh-incomplete').textContent = sshEvents.filter(e => e.type === 'conexion_sin_completar').length;
  $('#arm-description').textContent = `${summary.count} ${summary.count === 1 ? 'minuto con eventos' : 'minutos con eventos'}: ${summary.accepted} con acceso aceptado, ${summary.incomplete} con conexión sin completar y ${summary.both} con ambos. Cada minuto cuenta una vez aunque repita mensajes.`;
  const rules = $('#arm-rows'); rules.replaceChildren();
  for (const rule of summary.rules) {
    const row = element('tr');
    for (const text of [rule.from + ' → ' + rule.to, percent.format(rule.support), percent.format(rule.confidence), decimal.format(rule.lift)]) row.append(element('td', text));
    rules.append(row);
  }
  $('#arm-empty').textContent = summary.rules.length ? '' : 'No hay reglas: ningún minuto contiene ambos tipos de evento.';
  const rows = $('#ssh-rows'); rows.replaceChildren();
  for (const event of [...sshEvents].reverse()) {
    const row = element('tr'); row.append(element('td', format.format(new Date(event.date))),
      element('td', event.type === 'acceso_aceptado' ? 'Acceso aceptado' : 'Conexión sin completar', event.type === 'acceso_aceptado' ? 'green' : 'amber'));
    rows.append(row);
  }
  const chart = $('#ssh-chart'); chart.replaceChildren();
  const groups = [...summary.minutes.entries()].sort((a, b) => a[0] - b[0]);
  const max = Math.max(1, ...groups.map(([, group]) => group.accepted + group.incomplete));
  for (let tick = 0; tick <= max; tick++) {
    const y = 200 - tick / max * 170;
    chart.append(svgElement('line', { x1: 48, y1: y, x2: 740, y2: y, stroke: '#2b3a50' }),
      svgElement('text', { x: 36, y: y + 4, fill: '#b6c3d6', 'font-size': 13, 'text-anchor': 'end' }, tick));
  }
  const width = 680 / groups.length;
  for (let index = 0; index < groups.length; index++) {
    const [minute, group] = groups[index];
    const x = 56 + index * width;
    const accepted = group.accepted / max * 170, incomplete = group.incomplete / max * 170;
    const bar = svgElement('g');
    bar.append(svgElement('title', {}, `${minuteFormat.format(new Date(minute * 60000))}: ${group.accepted} accesos aceptados, ${group.incomplete} sin completar`));
    if (accepted) bar.append(svgElement('rect', { x, y: 200 - accepted, width: width - 18, height: accepted, fill: '#70dbc5', rx: 3 }));
    if (incomplete) bar.append(svgElement('rect', { x, y: 200 - accepted - incomplete, width: width - 18, height: incomplete, fill: '#ffc46b', rx: 3 }));
    chart.append(bar, svgElement('text', { x: x + (width - 18) / 2, y: 226, fill: '#b6c3d6', 'font-size': 13, 'text-anchor': 'middle' }, minuteFormat.format(new Date(minute * 60000))));
  }
}
$('#ssh-scenario').addEventListener('change', () => { sshEvents = sshScenario($('#ssh-scenario').value); renderSsh(); });
$('#download-csv').addEventListener('click', () => {
  const csv = 'fecha_observada,tipo_evento\n' + sshEvents.map(event => event.date + ',' + event.type).join('\n') + '\n';
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = element('a'); link.href = url; link.download = 'eventos-ssh-demo.csv';
  document.body.append(link); link.click(); link.remove();
  schedule(() => URL.revokeObjectURL(url), 1000);
});
renderAll(); renderSsh(); selectView(location.hash.slice(1), false);
