/* Real payments, broker and stock. Transport-loss/pending tests use named injections. */
const {chromium} = require('playwright');
const {execFileSync} = require('node:child_process');
const {randomUUID, createHash} = require('node:crypto');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const marker = 'pay-ui-' + randomUUID().replaceAll('-', '');
const email = marker + '@example.com', password = 'Ui-' + randomUUID();
const service = (name, code, ...args) => execFileSync('docker', ['compose', 'exec', '-T', name, 'python', '-c', code, ...args.map(String)], {encoding: 'utf8'}).trim();
const report = {scope: 'real payment/inventory/events; injected transport losses and 202 explicitly named', checks: [], cleanup: false};
const check = async (name, fn) => {await fn(); report.checks.push(name); console.log('OK:', name);};
let browser, user, product;
const attempts = id => JSON.parse(service('payment-service', `
import sys,json
from sqlalchemy import text
from app.database import engine
with engine.connect() as db:
 p={'id':int(sys.argv[1])}
 print(json.dumps({'attempts':db.execute(text('SELECT count(*) FROM payments WHERE order_id=:id'),p).scalar(),'paid':db.execute(text("SELECT count(*) FROM payments WHERE order_id=:id AND status='PAID'"),p).scalar(),'events':db.execute(text('SELECT count(*) FROM outbox_events WHERE aggregate_id=:id'),p).scalar()}))
`, id));
const stock = () => Number(service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db: print(db.get(Product,int(sys.argv[1])).stock)
`, product));
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
  context.on('page', p => p.on('pageerror', error => errors.push(error.message)));
  page.on('pageerror', error => errors.push(error.message));
  const created = await page.request.post('/api/auth/register', {data: {name: marker, email, password}});
  assert.equal(created.status(), 201); user = (await created.json()).id;
  const login = async p => {
    await p.goto(base + '#cuenta'); await p.reload();
    await p.locator('#login-email').fill(email); await p.locator('#login-password').fill(password);
    await p.locator('#login-form button').click(); await p.locator('#profile').waitFor({state: 'visible'});
  };
  const go = async (p, hash) => p.evaluate(value => {location.hash = value;}, hash);
  const ready = p => p.waitForFunction(() => !document.querySelector('#payment-form').hidden && !document.querySelector('#pay-button').disabled);
  const newOrder = async () => {
    await go(page, '#producto/' + product); await page.locator('#detail').waitFor({state: 'visible'});
    await page.locator('#add-button').click();
    await page.waitForFunction(() => document.querySelector('#add-status').textContent.includes('agregado'));
    await page.getByRole('link', {name: 'Ver mi carrito', exact: true}).click();
    await page.waitForFunction(() => document.querySelector('#cart-items').getAttribute('aria-busy') === 'false');
    await page.getByRole('link', {name: 'Revisar pedido', exact: true}).click();
    await page.locator('#confirm-order').click(); await ready(page);
    return Number(await page.locator('#order-number').textContent());
  };
  const paid = p => p.waitForFunction(() => document.querySelector('#payment-status').textContent.includes('aprobado') && document.querySelector('#pay-button').disabled === false && document.querySelector('#payment-form').hidden);
  const pay = async (value, p = page) => {await p.locator('#simulation-result').selectOption(value); await p.locator('#pay-button').click();};
  await login(page);
  let first;
  await check('creating order does not submit a payment automatically', async () => {
    first = await newOrder(); assert.equal(attempts(first).attempts, 0);
  });
  await check('three real simulated rejections preserve stock and produce no paid events', async () => {
    for (const [value, reason] of [['insufficient_funds', /fondos/], ['expired_card', /vencida/], ['card_declined', /emisor/]]) {
      await pay(value); await ready(page); assert.match(await page.locator('#payment-status').textContent(), reason);
      assert.notEqual(await page.locator('#payment-date').textContent(), 'Pendiente');
      assert.equal(stock(), 20);
    }
    assert.deepEqual(attempts(first), {attempts: 3, paid: 0, events: 0});
    const reservations = Number(service('product-service', `
import sys
from sqlalchemy import text
from app.database import engine
with engine.connect() as db:print(db.execute(text('SELECT count(*) FROM inventory_reservations WHERE order_id=:id'),{'id':int(sys.argv[1])}).scalar())
`, first)); assert.equal(reservations, 0);
    fs.mkdirSync('docs/frontend', {recursive: true});
    await page.screenshot({path: 'docs/frontend/pago-rechazado.png', fullPage: true});
  });
  await check('explicit approved retry creates one paid attempt, one stock discount and three destination events', async () => {
    await pay('approved'); await paid(page); assert.equal(stock(), 19);
    assert.deepEqual(attempts(first), {attempts: 4, paid: 1, events: 3});
    assert.equal(await page.locator('#payment-form').isVisible(), false);
  });
  await check('payment recovery endpoint requires auth and hides another owners attempt', async () => {
    assert.equal((await page.request.get(`/api/payments/orders/${first}/latest`)).status(), 401);
    const isolated = await browser.newContext({baseURL: base});
    // Reuse a valid but different subject signed only inside the trusted test service.
    const token = service('payment-service', `
from datetime import datetime,timedelta,timezone
from jose import jwt
from app.core.config import settings
print(jwt.encode({'sub':'2147480000','email':'other@example.com','role':'client','exp':datetime.now(timezone.utc)+timedelta(minutes=2)},settings.SECRET_KEY,algorithm=settings.JWT_ALGORITHM))
`);
    assert.equal((await isolated.request.get(`/api/payments/orders/${first}/latest`, {headers: {Authorization: 'Bearer ' + token}})).status(), 404);
    await isolated.close();
  });
  await check('lost successful payment response recovers latest attempt without a second POST', async () => {
    const id = await newOrder(); let posts = 0;
    await page.route('**/api/payments', async route => {posts++; await route.fetch(); await route.abort('failed');});
    await pay('approved'); await paid(page); await page.unroute('**/api/payments');
    assert.equal(posts, 1); assert.deepEqual(attempts(id), {attempts: 1, paid: 1, events: 3}); assert.equal(stock(), 18);
  });
  await check('injected pending response polls GET and resolves the same real paid attempt', async () => {
    const id = await newOrder(); let posts = 0, gets = 0;
    await page.route('**/api/payments', async route => {
      posts++; const response = await route.fetch(); const value = await response.json();
      await route.fulfill({status: 202, contentType: 'application/json', body: JSON.stringify({...value, status: 'PENDING', processed_at: null})});
    });
    await page.route('**/api/payments/orders/*/latest', async route => {gets++; await route.continue();});
    await pay('approved'); await paid(page); await page.unroute('**/api/payments'); await page.unroute('**/api/payments/orders/*/latest');
    assert.equal(posts, 1); assert.ok(gets >= 2); assert.equal(attempts(id).paid, 1); assert.equal(stock(), 17);
  });
  await check('request lost before server needs explicit same-simulation retry', async () => {
    const id = await newOrder(); let posts = 0;
    await page.route('**/api/payments', async route => {posts++; await route.abort('failed');});
    await pay('approved'); await page.locator('#resume-payment').waitFor({state: 'visible'});
    assert.equal(posts, 1); assert.equal(attempts(id).attempts, 0); assert.equal(await page.locator('#payment-form').isVisible(), false);
    await page.unroute('**/api/payments'); await page.locator('#resume-payment').click(); await paid(page);
    assert.equal(attempts(id).paid, 1); assert.equal(stock(), 16);
  });
  await check('two tabs approving the same order produce a single paid attempt and reservation', async () => {
    const id = await newOrder(); const other = await context.newPage(); await login(other);
    await go(other, '#carrito'); await other.locator('#recover-checkout').waitFor({state: 'visible'});
    await other.locator('#recover-checkout').click(); await ready(other);
    await Promise.all([pay('approved'), pay('approved', other)]);
    await Promise.all([paid(page), paid(other)]);
    assert.deepEqual(attempts(id), {attempts: 1, paid: 1, events: 3}); assert.equal(stock(), 15); await other.close();
  });
  await check('stock exhausted after checkout rejects approved simulation without paid events', async () => {
    const id = await newOrder();
    service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db: db.get(Product,int(sys.argv[1])).stock=0;db.commit()
`, product);
    await pay('approved'); await ready(page);
    assert.match(await page.locator('#payment-status').textContent(), /stock/);
    assert.deepEqual(attempts(id), {attempts: 1, paid: 0, events: 0});
    service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db: db.get(Product,int(sys.argv[1])).stock=15;db.commit()
`, product);
  });
  await check('failed preflight lookup blocks payment POST until a successful state refresh', async () => {
    const id = await newOrder(); let posts = 0;
    const listener = request => {if (request.method() === 'POST' && request.url().endsWith('/api/payments')) posts++;};
    page.on('request', listener);
    await page.route('**/api/payments/orders/*/latest', route => route.fulfill({status: 503, contentType: 'application/json', body: '{}'}));
    await pay('approved'); await page.locator('#payment-error').waitFor({state: 'visible'});
    assert.equal(posts, 0); assert.equal(attempts(id).attempts, 0);
    await page.unroute('**/api/payments/orders/*/latest');
    await page.locator('#refresh-payment').click(); await ready(page);
    await pay('approved'); await paid(page); assert.equal(stock(), 14); page.off('request', listener);
  });
  await check('reload/login restores successful payment; mobile fits and logout clears transaction details', async () => {
    await login(page); await go(page, '#carrito'); await page.locator('#recover-checkout').waitFor({state: 'visible'});
    await page.locator('#recover-checkout').click(); await paid(page);
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({path: 'docs/frontend/pago-aprobado-mobile.png', fullPage: true});
    await page.locator('#logout').click(); assert.equal(await page.locator('#payment-reference').textContent(), '');
    assert.equal(await page.locator('#payment-panel').isVisible(), false);
  });
  assert.deepEqual(errors, []); report.status = 'passed';
})().catch(error => {report.status = 'failed'; console.error(error.message); process.exitCode = 1;}).finally(async () => {
  if (browser) await browser.close();
  try {
    if (user) {
      // Let owned paid events drain before removing fixtures. Refuse cleanup of live work.
      service('payment-service', `
import sys,time
from sqlalchemy import text
from app.database import engine
deadline=time.monotonic()+40
with engine.connect() as db:
 while db.execute(text("SELECT count(*) FROM outbox_events WHERE payload->>'user_id'=:id AND published_at IS NULL"),{'id':sys.argv[1]}).scalar():
  db.rollback();assert time.monotonic()<deadline,'Owned outbox still pending';time.sleep(.25)
`, user);
      const ids = JSON.parse(service('order-service', `
import sys,json
from app.database import SessionLocal
from app.models import Order
with SessionLocal() as db: print(json.dumps([r.id for r in db.query(Order).filter(Order.user_id==int(sys.argv[1]))]))
`, user));
      for (const id of ids) {
        service('product-service', `
import sys,time
from sqlalchemy import text
from app.database import engine
deadline=time.monotonic()+40
with engine.connect() as db:
 while db.execute(text("SELECT count(*) FROM inventory_reservations WHERE order_id=:id AND status='RESERVED'"),{'id':int(sys.argv[1])}).scalar():
  db.rollback();assert time.monotonic()<deadline,'Owned reservation not consumed';time.sleep(.25)
`, id);
      }
      // Existing cleanup scopes every delete to the owned order/product/user IDs.
      const fixture = {id: product, name: marker};
      const userFixture = {id: user, email};
      execFileSync('python', ['-c', 'import sys,json;sys.path.insert(0,"tests");from smoke_inventory import cleanup;cleanup(json.loads(sys.argv[1]),json.loads(sys.argv[2]),json.loads(sys.argv[3]))', JSON.stringify(userFixture), JSON.stringify(fixture), JSON.stringify(ids.map(id => ({id})))], {stdio: ['ignore', 'pipe', 'pipe']});
    } else if (product) service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db: db.query(Product).filter(Product.id==int(sys.argv[1]),Product.name==sys.argv[2]).delete(synchronize_session=False);db.commit()
`, product, marker);
    report.cleanup = true;
  } catch (error) {report.cleanup = false; console.error('Owned fixture cleanup failed:', error.message.slice(0, 350)); process.exitCode = 1;}
  report.date = new Date().toISOString(); report.sha256 = {};
  for (const file of ['frontend/app/payments.js', 'frontend/app/commerce.js', 'frontend/app/index.html', 'frontend/app/styles.css', 'frontend/app/orders.js', 'services/payment-service/app/routers/payments.py', 'tests/frontend_payments.cjs', 'tests/payment_latest.py']) report.sha256[file] = createHash('sha256').update(fs.readFileSync(file, 'utf8').replaceAll('\r\n', '\n')).digest('hex');
  fs.mkdirSync('docs/frontend', {recursive: true}); fs.writeFileSync('docs/frontend/pagos.json', JSON.stringify(report, null, 2) + '\n');
});
