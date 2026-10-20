const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { test } = require('node:test');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

function browser() {
  const elements = new Map();
  const node = (selector) => {
    if (!elements.has(selector)) elements.set(selector, { innerHTML: '', textContent: '', className: '' });
    return elements.get(selector);
  };
  const context = vm.createContext({
    crypto: webcrypto, Intl, console,
    document: { querySelector: node, addEventListener() {} },
    // Hold initialization at its network boundary; tests drive rendered helpers explicitly.
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(readFileSync('app/static/app.js', 'utf8'), context);
  return { context, node };
}

test('claim table escapes agent-supplied text instead of creating markup', () => {
  const { context } = browser();
  context.claim = { id: 'SYN-1', patient_name: '<img src=x onerror=alert(1)>', patient_id: '<script>',
    service_type: 'Medical', service_date: '2026-01-01', amount: '125.00', status: 'Submitted' };
  const html = vm.runInContext('table([claim])', context);
  assert.ok(html.includes('&lt;img'));
  assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(!html.includes('<img'));
  assert.ok(html.includes('$125.00'));
});

test('API failures surface validation errors and do not retry unauthorized requests', async () => {
  const { context } = browser();
  vm.runInContext('config = { auth_mode: "development" }', context);
  let calls = 0;
  context.fetch = async () => { calls++; return { ok: false, json: async () => ({ detail: 'Requires Claims.Writer' }) }; };
  await assert.rejects(vm.runInContext('api("/claims")', context), /Requires Claims.Writer/);
  assert.equal(calls, 1);
  context.fetch = async () => ({ ok: false, json: async () => ({ detail: [{ loc: ['body', 'amount'], msg: 'Invalid amount' }] }) });
  await assert.rejects(vm.runInContext('api("/claims")', context), /amount: Invalid amount/);
});
