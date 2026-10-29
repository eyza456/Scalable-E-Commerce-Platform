const {chromium} = require('playwright');
const {execFileSync} = require('node:child_process');
const {randomUUID, createHash} = require('node:crypto');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const marker = 'history-ui-' + randomUUID().replaceAll('-', '');
const email = marker + '@example.com', password = 'Ui-' + randomUUID();
const report = {scope: 'real private order history/cancellation/payment; transport loss and 202 explicitly injected', checks: [], cleanup: false};
const service = (name, code, ...args) => execFileSync('docker', ['compose', 'exec', '-T', name, 'python', '-c', code, ...args.map(String)], {encoding: 'utf8'}).trim();
const check = async (name, fn) => {await fn(); report.checks.push(name); console.log('OK:', name);};
let browser, user, product, token;
const ids = [];
(async () => {
  product = Number(service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db:
 p=Product(name=sys.argv[1],price=12.30,stock=20);db.add(p);db.commit();print(p.id)
`, marker));
  browser = await chromium.launch({headless: true, channel: process.env.BROWSER_CHANNEL || 'msedge'});
  const base = process.env.FRONTEND_URL || 'http://127.0.0.1:8080/';
  const context = await browser.newContext({baseURL: base, viewport: {width: 1440, height: 1000}});
  const page = await context.newPage(), errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const created = await page.request.post('/api/auth/register', {data: {name: marker, email, password}});
  assert.equal(created.status(), 201); user = (await created.json()).id;
  token = (await (await page.request.post('/api/auth/login', {data: {email, password}})).json()).access_token;
  const auth = {Authorization: 'Bearer ' + token};
  const go = async hash => page.evaluate(value => {location.hash = value;}, hash);
  const open = async id => {await go('#pedidos/' + id); await page.locator('#history-detail').waitFor({state: 'visible'});};
  const apply = async status => {
    await go('#pedidos'); await page.locator('#order-filter').selectOption(status);
    await page.locator('#orders-filters button').click();
    await page.waitForFunction(() => document.querySelector('#orders-list').getAttribute('aria-busy') === 'false');
  };
  await check('guest cannot view private order history', async () => {
    await page.goto(base + '#pedidos'); await page.locator('#orders-login').waitFor({state: 'visible'});
    assert.equal(await page.locator('#orders-private').isVisible(), false);
  });
  await go('#cuenta'); await page.locator('#login-email').fill(email); await page.locator('#login-password').fill(password);
  await page.locator('#login-form button').click(); await page.locator('#profile').waitFor({state: 'visible'});
  await check('real empty history differs from service error', async () => {
    await apply(''); assert.match(await page.locator('#orders-status').textContent(), /No hay pedidos/);
    assert.equal(await page.locator('#orders-error').isVisible(), false);
  });
  // Create owned orders through the same public APIs. No administrative status edits.
  for (let n = 0; n < 12; n++) {
    assert.equal((await page.request.post('/api/cart/items', {headers: auth, data: {product_id: product, quantity: 1}})).status(), 201);
    const value = await page.request.post('/api/orders', {headers: auth}); assert.equal(value.status(), 201); ids.push((await value.json()).id);
  }
  await check('history paginates real orders and detail shows authoritative items/total', async () => {
    await apply(''); assert.equal(await page.locator('.history-card').count(), 10);
    await page.locator('#orders-next').click();
    await page.waitForFunction(() => document.querySelectorAll('.history-card').length === 2);
    await open(ids[0]); assert.match(await page.locator('#history-total').textContent(), /12,30/);
    assert.match(await page.locator('#history-items').textContent(), new RegExp(marker));
  });
  await check('confirmation dialog can be dismissed without cancellation', async () => {
    await page.locator('#cancel-order').click(); await page.locator('#cancel-dialog').waitFor({state: 'visible'});
    await page.locator('#keep-order').click();
    const value = await (await page.request.get('/api/orders/' + ids[0], {headers: auth})).json(); assert.equal(value.status, 'PENDING');
  });
  const cancel = async () => {await page.locator('#cancel-order').click(); await page.locator('#confirm-cancel').click();};
  await check('real pending cancellation and state filter return cancelled order', async () => {
    await cancel(); await page.waitForFunction(() => document.querySelector('#history-state').textContent === 'Cancelado');
    assert.equal(await page.locator('#cancel-order').isVisible(), false);
    await apply('CANCELLED'); assert.equal(await page.locator('.history-card').count(), 1);
    assert.match(await page.locator('.history-card').textContent(), new RegExp('#' + ids[0]));
  });
  await check('lost cancellation response recovers real cancelled state without second POST', async () => {
    await open(ids[1]); let posts = 0;
    await page.route('**/api/orders/*/cancel', async route => {posts++; await route.fetch(); await route.abort('failed');});
    await cancel(); await page.waitForFunction(() => document.querySelector('#history-state').textContent === 'Cancelado');
    assert.equal(posts, 1); await page.unroute('**/api/orders/*/cancel');
  });
  await check('injected cancelling response polls GET and reaches real cancelled state', async () => {
    await open(ids[2]); let posts = 0;
    await page.route('**/api/orders/*/cancel', async route => {
      posts++; const response = await route.fetch(); const value = await response.json();
      await route.fulfill({status: 202, contentType: 'application/json', body: JSON.stringify({...value, status: 'CANCELLING'})});
    });
    await cancel(); await page.waitForFunction(() => document.querySelector('#history-state').textContent === 'Cancelado');
    assert.equal(posts, 1); await page.unroute('**/api/orders/*/cancel');
  });
  await check('historical order payment approves from its own panel and removes cancellation', async () => {
    await open(ids[3]);
    await page.waitForFunction(() => !document.querySelector('#history-payment-form').hidden && !document.querySelector('#history-pay-button').disabled);
    await page.locator('#history-pay-button').click();
    await page.waitForFunction(() => document.querySelector('#history-payment-status').textContent.includes('aprobado'));
    await page.locator('#refresh-order').click();
    await page.waitForFunction(() => document.querySelector('#history-state').textContent === 'Pagado');
    assert.equal(await page.locator('#cancel-order').isVisible(), false);
    assert.equal((await page.request.post(`/api/orders/${ids[3]}/cancel`, {headers: auth})).status(), 409);
  });
  await check('foreign order detail stays private and history failure is recoverable', async () => {
    const other = await page.request.post('/api/auth/register', {data: {name: marker + '-other', email: marker + '-other@example.com', password}});
    const otherUser = await other.json();
    try {
      const otherToken = (await (await page.request.post('/api/auth/login', {data: {email: otherUser.email, password}})).json()).access_token;
      assert.deepEqual(await (await page.request.get('/api/orders', {headers: {Authorization: 'Bearer ' + otherToken}})).json(), []);
      assert.equal((await page.request.get('/api/orders/' + ids[0], {headers: {Authorization: 'Bearer ' + otherToken}})).status(), 404);
    } finally {
      service('user-service', `
import sys
from app.database import SeccionLocal
from app.models import User
with SeccionLocal() as db: db.query(User).filter(User.id==int(sys.argv[1])).delete(synchronize_session=False);db.commit()
`, otherUser.id);
    }
    await page.route('**/api/orders?*', route => route.fulfill({status: 503, contentType: 'application/json', body: '{}'}));
    await go('#pedidos'); await page.locator('#orders-error').waitFor({state: 'visible'});
    assert.equal(await page.locator('.history-card').count(), 0); await page.unroute('**/api/orders?*');
    await page.locator('#refresh-orders').click(); await page.waitForFunction(() => document.querySelector('#orders-list').getAttribute('aria-busy') === 'false');
    assert.equal(await page.locator('#orders-error').isVisible(), false);
  });
  await check('mobile history/detail fit; logout clears private items and payment reference', async () => {
    await apply(''); fs.mkdirSync('docs/frontend', {recursive: true});
    await page.screenshot({path: 'docs/frontend/historial-desktop.png', fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({path: 'docs/frontend/historial-mobile.png', fullPage: true});
    await open(ids[0]); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({path: 'docs/frontend/pedido-cancelado-mobile.png', fullPage: true});
    await page.locator('#logout').click(); assert.equal(await page.locator('#history-items').textContent(), '');
    assert.equal(await page.locator('#history-payment-reference').textContent(), '');
    await go('#pedidos'); assert.equal(await page.locator('#orders-private').isVisible(), false);
  });
  assert.deepEqual(errors, []); report.status = 'passed';
})().catch(error => {report.status = 'failed'; console.error(error.message); process.exitCode = 1;}).finally(async () => {
  if (browser) await browser.close();
  try {
    if (user) {
      service('payment-service', `
import sys,time
from sqlalchemy import text
from app.database import engine
deadline=time.monotonic()+40
with engine.connect() as db:
 while db.execute(text("SELECT count(*) FROM outbox_events WHERE payload->>'user_id'=:id AND published_at IS NULL"),{'id':sys.argv[1]}).scalar():
  db.rollback();assert time.monotonic()<deadline;time.sleep(.25)
`, user);
      if (ids.length) service('product-service', `
import sys,time
from sqlalchemy import text
from app.database import engine
deadline=time.monotonic()+40
with engine.connect() as db:
 while db.execute(text("SELECT count(*) FROM inventory_reservations WHERE user_id=:id AND status='RESERVED'"),{'id':int(sys.argv[1])}).scalar():
  db.rollback();assert time.monotonic()<deadline;time.sleep(.25)
`, user);
      execFileSync('python', ['-c', 'import sys,json;sys.path.insert(0,"tests");from smoke_inventory import cleanup;cleanup(json.loads(sys.argv[1]),json.loads(sys.argv[2]),json.loads(sys.argv[3]))', JSON.stringify({id: user, email}), JSON.stringify({id: product, name: marker}), JSON.stringify(ids.map(id => ({id})))], {stdio: ['ignore', 'pipe', 'pipe']});
    }
    report.cleanup = true;
  } catch {report.cleanup = false; console.error('Owned fixture cleanup failed'); process.exitCode = 1;}
  report.date = new Date().toISOString(); report.sha256 = {};
  for (const file of ['frontend/app/orders.js', 'frontend/app/app.js', 'frontend/app/index.html', 'frontend/app/styles.css', 'frontend/app/profile.js', 'tests/frontend_orders.cjs']) report.sha256[file] = createHash('sha256').update(fs.readFileSync(file, 'utf8').replaceAll('\r\n', '\n')).digest('hex');
  fs.mkdirSync('docs/frontend', {recursive: true}); fs.writeFileSync('docs/frontend/pedidos.json', JSON.stringify(report, null, 2) + '\n');
});
