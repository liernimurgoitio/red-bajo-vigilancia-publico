import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';

test('la entrega de soporte fija el modo ficticio y sus archivos coinciden con el manifiesto', async () => {
  const manifest = JSON.parse(await readFile(new URL('../demo/laguntza-build.json', import.meta.url), 'utf8'));
  const index = await readFile(new URL('../demo/soporte/index.html', import.meta.url), 'utf8');
  assert.match(index, /name="laguntza-mode" content="demo-integrada"/);
  for (const [file, expected] of Object.entries(manifest.sha256)) {
    assert.ok(!file.includes('..') && !file.startsWith('/'));
    const data = await readFile(new URL('../demo/soporte/' + file, import.meta.url));
    assert.equal(createHash('sha256').update(data).digest('hex'), expected, file);
  }
  for (const [, path] of index.matchAll(/(?:src|href)="(\.\/[^"?#]+)"/g)) {
    await readFile(new URL('../demo/soporte/' + path, import.meta.url));
  }
});

test('el inventario enlaza con la entrega local de soporte', async () => {
  const index = await readFile(new URL('../demo/index.html', import.meta.url), 'utf8');
  const app = await readFile(new URL('../demo/app.mjs', import.meta.url), 'utf8');
  assert.match(index, /href="soporte\//);
  assert.match(app, /mode: 'demo-integrada'/);
  assert.match(app, /equipo: device.id/);
});
