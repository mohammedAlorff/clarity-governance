// Exercise inspection controls without a browser or external dependencies.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const vm = require('node:vm');

// Only the DOM surface used by this application. Parsing rendered markup keeps
// localization tests at the data/chrome boundary without adding dependencies.
const decode = text => text.replace(/&(amp|lt|gt|quot|#39|nbsp);/g,
  (_, entity) => ({ amp: '&', lt: '<', gt: '>', quot: '"', '#39': "'", nbsp: '\u00a0' }[entity]));
function domElement(tagName = 'div', attributes = {}) {
  const node = {
    tagName: tagName.toUpperCase(), attributes, childNodes: [], handlers: {}, parentElement: null,
    dataset: Object.fromEntries(Object.entries(attributes).filter(([key]) => key.startsWith('data-')).map(([key, value]) => [key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), value])),
    getAttribute(name) { return this.attributes[name] ?? null; },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(event, handler) { this.handlers[event] = handler; },
    matches(selector) {
      return selector.split(',').some(part => {
        const selectors = part.trim().match(/\[[^\]]+\]|\.[\w-]+|[\w-]+/g) || [];
        return selectors.every(item => {
          if (item.startsWith('.')) return (this.attributes.class || '').split(/\s+/).includes(item.slice(1));
          if (!item.startsWith('[')) return this.tagName === item.toUpperCase();
          const [, name, value] = item.match(/^\[([^=\]]+)(?:=["']?([^"'\]]*)["']?)?\]$/);
          return value === undefined ? this.getAttribute(name) !== null : this.getAttribute(name) === value;
        });
      });
    },
    closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector); },
    querySelectorAll(selector) {
      return this.childNodes.flatMap(child => child.tagName ? [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)] : []);
    },
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; },
    get textContent() { return this.childNodes.map(child => child.tagName ? child.textContent : child.nodeValue).join(''); },
    set textContent(value) { this.childNodes = [{ nodeValue: String(value), parentElement: this }]; },
    get innerHTML() { return this.markup || ''; },
    set innerHTML(value) { this.markup = value; parseHTML(this, value); },
    get id() { return this.attributes.id || ''; },
    get disabled() { return this.getAttribute('disabled') !== null; },
    set disabled(value) { if (value) this.setAttribute('disabled', ''); else this.removeAttribute('disabled'); },
    get value() { return this.editedValue ?? (this.tagName === 'TEXTAREA' ? this.textContent : this.tagName === 'SELECT' ? (this.querySelector('[selected]') || this.querySelector('option'))?.value : this.attributes.value || ''); },
    set value(value) { this.editedValue = value; },
    focus() {}, setSelectionRange() {},
    showModal() { this.open = true; }, close() { this.open = false; }
  };
  node.classList = { toggle() {} };
  return node;
}
function parseHTML(root, html) {
  root.childNodes = [];
  const stack = [root];
  for (const token of html.match(/<!--[^]*?-->|<![^>]*>|<[^>]*>|[^<]+/g) || []) {
    if (token.startsWith('<!')) continue;
    if (token.startsWith('</')) { if (stack.length > 1) stack.pop(); continue; }
    const parent = stack.at(-1);
    if (token.startsWith('<')) {
      const [, tagName] = token.match(/^<([\w-]+)/) || [];
      if (!tagName) continue;
      const attributes = {};
      for (const match of token.slice(tagName.length + 1, -1).matchAll(/([^\s=/>]+)(?:="([^"]*)"|='([^']*)'|=([^\s>]+))?/g)) {
        attributes[match[1]] = decode(match[2] ?? match[3] ?? match[4] ?? '');
      }
      const child = domElement(tagName, attributes);
      child.parentElement = parent;
      parent.childNodes.push(child);
      if (!['input', 'br', 'hr', 'meta', 'link', 'img'].includes(tagName) && !token.endsWith('/>')) stack.push(child);
    } else parent.childNodes.push({ nodeValue: decode(token), parentElement: parent });
  }
}

function workspace({ render = false } = {}) {
  const document = domElement('document');
  // Inline bootstrap is tested through app.js; exclude script/style contents
  // from this small markup parser.
  document.innerHTML = readFileSync(join(__dirname, '../src/governance/static/index.html'), 'utf8').replace(/<script\b[^>]*>[^]*?<\/script>/g, '');
  document.documentElement = document.querySelector('html');
  document.documentElement.lang = 'en';
  document.getElementById = id => document.querySelector(`[id="${id}"]`);
  document.createTreeWalker = root => {
    const textNodes = node => node.childNodes.flatMap(child => child.tagName ? textNodes(child) : [child]);
    const nodes = textNodes(root);
    return { nextNode: () => nodes.shift() || null };
  };
  const storage = new Map();
  const context = vm.createContext({
    document, NodeFilter: { SHOW_TEXT: 4 }, performance: { now: () => 1000 },
    localStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    window: { addEventListener() {} }, location: { hash: '' },
    fetch: () => new Promise(() => {})
  });
  vm.runInContext(readFileSync(join(__dirname, '../src/governance/static/app.js'), 'utf8'), context);
  if (!render) vm.runInContext('render = () => {}; notify = () => {};', context);
  vm.runInContext("app.busy = false; app.state = { source: { connected: true, mode: 'mysql', name: 'Overview' }, settings: {}, schema: { name: 'Privacy', tables: [] } };", context);
  return { context, document, element: document.getElementById, run: code => vm.runInContext(code, context) };
}

test('a blocked readiness check never starts inspection', async () => {
  const page = workspace();
  const paths = [];
  page.context.request = async path => { paths.push(path); return { ready: false, issues: [] }; };
  await page.run('prepareInspection(true)');
  assert.deepEqual(paths, ['/api/inspect/preflight']);
  assert.equal(page.run('app.busy'), false);
});

test('check readiness does not start inspection even when ready', async () => {
  const page = workspace();
  const paths = [];
  page.context.request = async path => { paths.push(path); return { ready: true, issues: [] }; };
  await page.run('prepareInspection(false)');
  assert.deepEqual(paths, ['/api/inspect/preflight']);
});

test('starting uses the same explicit limits for preflight and inspection', async () => {
  const page = workspace();
  const requests = [];
  page.context.request = async (path, body) => {
    requests.push({ path, body: JSON.parse(JSON.stringify(body)) });
    return { ready: true, issues: [] };
  };
  page.run("app.inspectionMode = 'fixed'; app.limits.max_calls = 100;");
  await page.run('prepareInspection(true)');
  assert.equal(requests[1].path, '/api/inspect');
  assert.deepEqual(requests[0].body, requests[1].body);
  assert.equal(requests[1].body.limits.max_calls, 100);
  assert.equal(requests[1].body.mode, 'fixed');
  assert.equal(page.run('app.busy'), false);
});

test('input edits invalidate readiness and remain in the rendered settings', () => {
  const page = workspace();
  page.run('app.preflight = { ready: true };');
  page.element('main').handlers.input({ target: {
    id: 'limit-max_calls', dataset: { limit: 'max_calls' }, value: '100', matches: () => false
  } });
  assert.equal(page.run('app.preflight'), null);
  assert.match(page.run('inspectionSettings()'), /id="limit-max_calls"[^>]+value="100"/);
});

test('a preflight transport failure releases the busy state and never inspects', async () => {
  const page = workspace();
  const paths = [];
  page.context.request = async path => { paths.push(path); throw new Error('offline'); };
  await page.run('prepareInspection(true)');
  assert.deepEqual(paths, ['/api/inspect/preflight']);
  assert.equal(page.run('app.busy'), false);
});

const proposalFixture = {
  id: 'p1', kind: 'rule', status: 'draft', version: 1,
  title: 'Overview', description: 'Review queue',
  target: { table: 'Description', column: 'columns' },
  evidence: ['3 rows', 'Source connected'], assumptions: ['Privacy'],
  rule: { metric_id: 'pattern', target: { table: 'Description', column: 'columns' }, parameters: { pattern: 'Approved' } },
  reviewer: 'Reviewer', history: [{ version: 0, title: 'Quality report', description: 'Tables', reviews: [{ action: 'edit', reviewer: 'Reviewer', note: 'Run approved checks' }] }]
};

function reviewWorkspace() {
  const page = workspace({ render: true });
  page.context.proposalFixture = structuredClone(proposalFixture);
  page.run("app.state.proposals = [proposalFixture]; app.view = 'review'; render();");
  return page;
}

test('language switching preserves exact source identifiers and data types', () => {
  const page = workspace({ render: true });
  page.run("app.view = 'schema'; app.state.schema.tables = [{ name: 'Review queue', columns: [{ name: 'columns', data_type: 'Type', key: 'Key' }] }]; render(); toggleLanguage();");
  assert.equal(page.element('source-status').textContent, 'Overview');
  assert.match(page.element('sidebar-source').textContent, /^Privacy ·/);
  assert.match(page.element('main').querySelector('.toolbar').textContent, /^Privacy ·/);
  assert.equal(page.element('main').querySelector('.schema-table').querySelector('strong').textContent, 'Review queue');
  assert.deepEqual(page.element('main').querySelectorAll('td').map(node => node.textContent), ['columns', 'Type', 'لا', 'Key']);
  assert.equal(page.element('current-page').textContent, 'مستكشف المخطط');
});

test('localizing proposal chrome never translates evidence, assumptions, or review history', () => {
  const page = reviewWorkspace();
  page.run('toggleLanguage();');
  const card = page.element('main').querySelector('.proposal-card');
  assert.equal(card.querySelector('h2').textContent, 'Overview');
  assert.equal(card.querySelector('.proposal-description').textContent, 'Review queue');
  assert.deepEqual(card.querySelectorAll('li').map(node => node.textContent), ['3 rows', 'Source connected', 'Privacy']);
  assert.match(card.querySelector('.proposal-history').textContent, /Quality report/);
  assert.match(card.querySelector('.review-event').textContent, /Reviewer.*Run approved checks/);
  assert.deepEqual(JSON.parse(card.querySelector('pre').textContent), proposalFixture.rule);
  assert.match(card.querySelector('.proposal-actions').textContent, /اعتماد/);
});

test('dictionary descriptions and evidence retain their source language', () => {
  const page = workspace({ render: true });
  page.run("app.view = 'dictionary'; app.dictionary = { columns: [{ table: 'Tables', column: 'Columns', data_type: 'Type', description: 'Description', evidence: ['3 rows'], status: 'approved' }] }; render(); toggleLanguage();");
  const cells = page.element('main').querySelectorAll('td');
  assert.match(cells[1].textContent, /^Type/);
  assert.match(cells[2].textContent, /^Description/);
  assert.equal(cells[2].querySelector('.history-entry').textContent, '3 rows');
  assert.equal(cells[3].textContent, 'معتمد');
});

test('dictionary labels and run statuses are fully localized in Arabic', () => {
  const page = workspace({ render: true });
  page.run("app.view = 'dictionary'; app.state.schema = { tables: [] }; app.dictionary = { columns: [{ table: 'film', column: 'name', data_type: 'varchar', status: 'not_documented' }] }; render(); toggleLanguage();");
  const content = page.element('main').textContent;
  assert.match(content, /مرجع حيّ لمخططك، يميّز بوضوح بين الأوصاف المقترحة والمعتمدة/);
  assert.match(content, /عمود · أوصاف المصدر وحالة المراجعة/);
  assert.match(content, /لا يوجد وصف تمت مراجعته بعد/);
  assert.match(content, /غير موثق/);
});

test('language and theme changes preserve live control values and open sections', () => {
  const page = workspace({ render: true });
  page.run('render();');
  const source = page.element('source-mode');
  source.value = 'demo';
  const settings = page.element('main').querySelector('.inspection-settings');
  settings.open = true;
  page.run('toggleLanguage(); toggleTheme(); toggleLanguage();');
  assert.ok(page.element('source-mode') === source, 'switching languages must preserve the live source select');
  assert.equal(page.element('source-mode').value, 'demo');
  assert.equal(page.element('main').querySelector('.inspection-settings').open, true);
  assert.equal(page.document.querySelector('[data-en="Schema profiler"]').textContent, 'Schema profiler');
});

test('opening an Arabic review dialog localizes controls without altering editable values', () => {
  const page = reviewWorkspace();
  page.run("toggleLanguage(); openReview('edit', 'p1');");
  assert.equal(page.element('dialog-title').textContent, 'تعديل المقترح · إنشاء مسودة جديدة');
  assert.equal(page.element('dialog-submit').textContent, 'احفظ المسودة الجديدة');
  const content = page.element('dialog-content');
  assert.equal(content.querySelector('[name="description"]').value, 'Review queue');
  assert.equal(content.querySelector('[name="evidence"]').value, '3 rows\nSource connected');
  assert.deepEqual(JSON.parse(content.querySelector('[name="rule"]').value), proposalFixture.rule);
  const note = content.querySelector('[name="note"]');
  note.value = 'Approved — ملاحظة لم تحفظ';
  page.run('toggleLanguage(); toggleTheme(); toggleLanguage();');
  assert.ok(content.querySelector('[name="note"]') === note, 'switching languages must preserve the edited note');
  assert.equal(note.value, 'Approved — ملاحظة لم تحفظ');
  assert.equal(content.querySelector('[name="description"]').value, 'Review queue');
  assert.deepEqual(JSON.parse(content.querySelector('[name="rule"]').value), proposalFixture.rule);
});

test('cached disconnected workspaces expose saved data but disable mutation controls', async () => {
  const page = reviewWorkspace();
  page.run('app.state.source.connected = false; render();');
  assert.match(page.element('main').textContent, /Saved results are available/);
  assert.match(page.element('main').textContent, /Connecting starts a new inspection scope/);
  assert.equal(page.element('command-inspect').disabled, true);
  assert.equal(page.element('command-run').disabled, true);
  for (const button of page.element('main').querySelectorAll('[data-action]')) assert.equal(button.disabled, true, button.dataset.action);
  assert.equal(page.element('main').querySelector('.proposal-card').querySelector('h2').textContent, 'Overview');
  const requests = [];
  page.context.request = async path => { requests.push(path); return {}; };
  await page.run("prepareInspection(true); openReview('approve', 'p1');");
  assert.deepEqual(requests, []);
  assert.equal(page.run('app.dialog'), null);
  page.run("app.view = 'overview'; render();");
  assert.equal(page.element('main').querySelector('[data-action="connect"]').disabled, false);
  for (const action of ['preflight', 'inspect', 'run']) assert.equal(page.element('main').querySelector(`[data-action="${action}"]`).disabled, true, action);
});

test('a cached disconnected schema can load and export its saved dictionary', async () => {
  const page = workspace({ render: true });
  page.run("app.state.source.connected = false; app.view = 'dictionary';");
  const requests = [];
  page.context.request = async path => {
    requests.push(path);
    return { columns: [{ table: 'saved_table', column: 'saved_column', description: 'Saved description', status: 'approved' }] };
  };
  await page.run('loadDictionary()');
  assert.deepEqual(requests, ['/api/dictionary']);
  assert.match(page.element('main').textContent, /saved_column/);
  assert.match(page.element('main').textContent, /Saved description/);
  assert.equal(page.element('main').querySelector('[download]').getAttribute('href'), '/api/export/dictionary');
});
