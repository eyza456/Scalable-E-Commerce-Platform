/* Real cart/order APIs; network faults and pending responses are explicitly injected. */
const {chromium} = require('playwright');
const {execFileSync} = require('node:child_process');
const {randomUUID, createHash} = require('node:crypto');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const marker = 'cart-ui-' + randomUUID().replaceAll('-', '');
const email = marker + '@example.com', password = 'Ui-' + randomUUID();
const report = {scope: 'real cart and checkout through frontend/gateway; injected faults named explicitly', checks: [], cleanup: false};
const service = (name, code, ...args) => execFileSync('docker', ['compose', 'exec', '-T', name, 'python', '-c', code, ...args.map(String)], {encoding: 'utf8'}).trim();
const check = async (name, fn) => {await fn(); report.checks.push(name); console.log('OK:', name);};
let browser, user, product;
function setProduct(price, stock) {
  service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db:
 p=db.get(Product,int(sys.argv[1]));p.price=sys.argv[2];p.stock=int(sys.argv[3]);db.commit()
`, product, price, stock);
}
function countOrders() {
  return Number(service('order-service', `
import sys
from app.database import SessionLocal
from app.models import Order
with SessionLocal() as db: print(db.query(Order).filter(Order.user_id==int(sys.argv[1])).count())
`, user));
}
(async () => {
  product = Number(service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db:
 p=Product(name=sys.argv[1],price=12.30,stock=10);db.add(p);db.commit();print(p.id)
`, marker));
  browser = await chromium.launch({headless: true, channel: process.env.BROWSER_CHANNEL || 'msedge'});
  const base = process.env.FRONTEND_URL || 'http://127.0.0.1:8080/';
  const context = await browser.newContext({baseURL: base, viewport: {width: 1440, height: 1000}});
  const page = await context.newPage(), errors = [];
  context.on('page', p => p.on('pageerror', error => errors.push(error.message)));
  page.on('pageerror', error => errors.push(error.message));
  const result = await page.request.post('/api/auth/register', {data: {name: marker, email, password}});
  assert.equal(result.status(), 201); user = (await result.json()).id;
  const wait = (p, fn, arg) => p.waitForFunction(fn, arg);
  const readyCart = p => wait(p, () => document.querySelector('#cart-items').getAttribute('aria-busy') === 'false' && !document.querySelector('#cart-private').hidden);
  const login = async p => {
    await p.goto(base + '#cuenta'); await p.reload();
    await p.locator('#login-email').fill(email); await p.locator('#login-password').fill(password);
    await p.locator('#login-form button').click(); await p.locator('#profile').waitFor({state: 'visible'});
  };
  const detail = async p => {
    await p.goto(base + '#producto/' + product);
    // Session is memory-only, so same-page hash navigation is used after login.
    if (await p.locator('#logout').isHidden()) {
      await p.evaluate(() => {location.hash = '#cuenta';});
      await p.locator('#login-email').fill(email); await p.locator('#login-password').fill(password);
      await p.locator('#login-form button').click(); await p.locator('#profile').waitFor({state: 'visible'});
      await p.evaluate(id => {location.hash = '#producto/' + id;}, product);
    }
    await p.locator('#detail').waitFor({state: 'visible'});
  };
  const add = async (quantity = 1) => {
    await detail(page); await page.locator('#add-quantity').fill(String(quantity));
    await page.locator('#add-button').click(); await wait(page, () => document.querySelector('#add-status').textContent.includes('agregado'));
    await page.getByRole('link', {name: 'Ver mi carrito', exact: true}).click(); await readyCart(page);
  };
  const review = async p => {
    await p.getByRole('link', {name: 'Revisar pedido', exact: true}).click();
    await wait(p, () => !document.querySelector('#confirm-order').hidden && !document.querySelector('#confirm-order').disabled);
  };
  const confirm = async p => {
    await p.locator('#confirm-order').click(); await p.locator('#order-result').waitFor({state: 'visible'});
  };
  await check('guest cart requires login and exposes no private content', async () => {
    await page.goto(base + '#carrito'); await page.locator('#cart-view .session-needed').waitFor({state: 'visible'});
    assert.equal(await page.locator('#cart-private').isVisible(), false);
  });
  await login(page);
  await check('real add, quantity update and removal preserve server totals', async () => {
    await add(2); assert.match(await page.locator('#cart-total').textContent(), /24,60/);
    await page.locator('.cart-controls input').fill('1'); await page.getByRole('button', {name: 'Actualizar', exact: true}).click();
    await wait(page, () => document.querySelector('#cart-total').textContent.includes('12,30'));
    await page.getByRole('button', {name: 'Quitar', exact: true}).click(); await page.locator('.empty-cart').waitFor({state: 'visible'});
    assert.equal(await page.locator('#cart-summary').isVisible(), false);
  });
  await check('lost add acknowledgement does not automatically repeat mutation', async () => {
    await detail(page); let posts = 0;
    await page.route('**/api/cart/items', async route => {posts++; await route.fetch(); await route.abort('failed');});
    await page.locator('#add-button').click(); await page.locator('#add-error').waitFor({state: 'visible'});
    assert.match(await page.locator('#add-error').textContent(), /No se confirmó/); assert.equal(posts, 1);
    assert.equal(await page.locator('#add-button').isDisabled(), true); await page.unroute('**/api/cart/items');
    await page.getByRole('link', {name: 'Ver mi carrito', exact: true}).click(); await readyCart(page);
    assert.equal(await page.locator('.cart-controls input').inputValue(), '1');
  });
  await check('checkout rejects changed price and quantity update refreshes price', async () => {
    setProduct('13.30', 10); await review(page); await page.locator('#confirm-order').click();
    await page.locator('#checkout-error').waitFor({state: 'visible'}); assert.match(await page.locator('#checkout-error').textContent(), /precio/);
    assert.equal(countOrders(), 0);
    await page.getByRole('link', {name: 'Volver al carrito'}).click(); await readyCart(page);
    await page.getByRole('button', {name: 'Actualizar', exact: true}).click();
    await wait(page, () => document.querySelector('#cart-total').textContent.includes('13,30'));
  });
  await check('checkout rejects depleted stock without order or extra mutation', async () => {
    setProduct('13.30', 0); await review(page); await page.locator('#confirm-order').click();
    await page.locator('#checkout-error').waitFor({state: 'visible'}); assert.match(await page.locator('#checkout-error').textContent(), /stock/);
    assert.equal(countOrders(), 0); setProduct('13.30', 10);
    await page.getByRole('link', {name: 'Volver al carrito'}).click(); await readyCart(page);
    await page.getByRole('button', {name: 'Actualizar', exact: true}).click(); await readyCart(page);
  });
  await check('cart changed in another client requires review instead of silently confirming new contents', async () => {
    await review(page);
    const response = await page.request.post('/api/auth/login', {data: {email, password}});
    const token = (await response.json()).access_token;
    const changed = await page.request.put(`/api/cart/items/${product}`, {headers: {Authorization: 'Bearer ' + token}, data: {quantity: 2}});
    assert.equal(changed.status(), 200);
    await page.locator('#confirm-order').click(); await page.locator('#checkout-error').waitFor({state: 'visible'});
    assert.match(await page.locator('#checkout-error').textContent(), /otra sesión/);
    assert.equal(await page.locator('#confirm-order').isDisabled(), true); assert.equal(countOrders(), 0);
    await page.getByRole('link', {name: 'Volver al carrito'}).click(); await readyCart(page);
    assert.equal(await page.locator('.cart-controls input').inputValue(), '2');
    await page.locator('.cart-controls input').fill('1');
    await page.getByRole('button', {name: 'Actualizar', exact: true}).click();
    await wait(page, () => document.querySelector('#cart-total').textContent.includes('13,30'));
  });
  await check('lost checkout response recovers the existing order without a second POST', async () => {
    await review(page); let posts = 0;
    await page.route('**/api/orders', async route => {posts++; await route.fetch(); await route.abort('failed');});
    await confirm(page); assert.equal(posts, 1); assert.equal(countOrders(), 1);
    assert.match(await page.locator('#order-status').textContent(), /Pendiente de pago/);
    await page.unroute('**/api/orders');
    await page.getByRole('link', {name: 'Volver al carrito'}).click(); await readyCart(page);
    await page.locator('.empty-cart').waitFor({state: 'visible'});
  });
  await check('reload and new login recover last checkout through the private cart', async () => {
    await login(page); await page.getByRole('link', {name: /^Carrito/}).click(); await readyCart(page);
    await page.locator('#recover-checkout').click(); await page.locator('#order-result').waitFor({state: 'visible'});
    assert.equal(countOrders(), 1);
  });
  await check('request lost before reaching server offers explicit retry with the same cart version', async () => {
    await add(); await review(page); const keys = [];
    await page.route('**/api/orders', async route => {keys.push(route.request().headers()['idempotency-key']); await route.abort('failed');});
    await page.locator('#confirm-order').click(); await page.locator('#resume-order').waitFor({state: 'visible'});
    assert.equal(countOrders(), 1); await page.unroute('**/api/orders');
    await page.route('**/api/orders', async route => {keys.push(route.request().headers()['idempotency-key']); await route.continue();});
    await page.locator('#resume-order').click(); await page.locator('#order-result').waitFor({state: 'visible'});
    assert.equal(keys.length, 2); assert.equal(keys[0], keys[1]); assert.equal(countOrders(), 2); await page.unroute('**/api/orders');
  });
  await check('injected pending response polls only GET and resolves real order', async () => {
    await add(); await review(page); let posts = 0, gets = 0;
    await page.route('**/api/orders', async route => {
      posts++; const response = await route.fetch(); const result = await response.json();
      await route.fulfill({status: 202, contentType: 'application/json', body: JSON.stringify({checkout_id: result.checkout_id, checkout_status: 'PENDING'})});
    });
    await page.route('**/api/orders/checkouts/*', async route => {gets++; await route.continue();});
    await confirm(page); assert.equal(posts, 1); assert.ok(gets >= 1); assert.equal(countOrders(), 3);
    await page.unroute('**/api/orders'); await page.unroute('**/api/orders/checkouts/*');
  });
  await check('two logged-in tabs confirming the same cart receive one order', async () => {
    await add(); const other = await context.newPage(); await login(other);
    await other.getByRole('link', {name: /^Carrito/}).click(); await readyCart(other);
    await review(page); await review(other);
    await Promise.all([confirm(page), confirm(other)]);
    assert.equal(await page.locator('#order-number').textContent(), await other.locator('#order-number').textContent());
    assert.equal(countOrders(), 4); await other.close();
  });
  await add();
  fs.mkdirSync('docs/frontend', {recursive: true});
  await page.screenshot({path: 'docs/frontend/carrito-desktop.png', fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  await check('cart and checkout fit mobile and logout removes private order content', async () => {
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({path: 'docs/frontend/carrito-mobile.png', fullPage: true});
    await review(page); assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({path: 'docs/frontend/checkout-mobile.png', fullPage: true});
    await page.locator('#logout').click();
    await page.getByRole('link', {name: /^Carrito/}).click();
    assert.equal(await page.locator('#cart-private').isVisible(), false); assert.equal(await page.locator('#cart-items').textContent(), '');
  });
  assert.deepEqual(errors, []); report.status = 'passed';
})().catch(error => {report.status = 'failed'; console.error(error.message); process.exitCode = 1;}).finally(async () => {
  if (browser) await browser.close();
  try {
    if (user) {
      service('order-service', `
import sys
from sqlalchemy import text
from app.database import engine
with engine.begin() as db:
 p={'id':int(sys.argv[1])}
 db.execute(text('DELETE FROM order_items WHERE order_id IN (SELECT id FROM orders WHERE user_id=:id)'),p)
 db.execute(text('DELETE FROM checkouts WHERE user_id=:id'),p)
 db.execute(text('DELETE FROM orders WHERE user_id=:id'),p)
`, user);
      service('cart-service', 'import sys;from app.redis_client import redis_client;redis_client.delete("cart:"+sys.argv[1])', user);
      service('user-service', `
import sys
from app.database import SeccionLocal
from app.models import User
with SeccionLocal() as db:
 db.query(User).filter(User.id==int(sys.argv[1]),User.email==sys.argv[2]).delete(synchronize_session=False);db.commit()
`, user, email);
    }
    if (product) service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db:
 db.query(Product).filter(Product.id==int(sys.argv[1]),Product.name==sys.argv[2]).delete(synchronize_session=False);db.commit()
`, product, marker);
    report.cleanup = true;
  } catch {report.cleanup = false; console.error('Cleanup failed for owned fixtures'); process.exitCode = 1;}
  report.date = new Date().toISOString(); report.sha256 = {};
  for (const file of ['frontend/app/app.js', 'frontend/app/commerce.js', 'frontend/app/payments.js', 'frontend/app/index.html', 'frontend/app/styles.css', 'frontend/app/profile.js', 'frontend/app/orders.js', 'tests/frontend_commerce.cjs']) report.sha256[file] = createHash('sha256').update(fs.readFileSync(file, 'utf8').replaceAll('\r\n', '\n')).digest('hex');
  fs.mkdirSync('docs/frontend', {recursive: true}); fs.writeFileSync('docs/frontend/carrito-checkout.json', JSON.stringify(report, null, 2) + '\n');
});
