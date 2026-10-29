/* Browser integration against the real frontend, gateway and databases.
 * Needs Playwright + Edge, Docker Compose running and the frontend on port 8080.
 * Creates and removes only fixtures bearing its unique marker.
 */
const { chromium } = require('playwright');
const { execFileSync } = require('node:child_process');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const marker = 'ui-' + randomUUID().replaceAll('-', '');
const email = marker + '@example.com';
const password = 'Ui-' + randomUUID();
const report = {scope: 'real frontend + gateway; owned fixtures; injected failures explicitly identified', checks: [], cleanup: false};
const service = (name, code, ...args) => execFileSync('docker', ['compose', 'exec', '-T', name, 'python', '-c', code, ...args], {encoding: 'utf8'}).trim();
const check = async (name, action) => { await action(); report.checks.push(name); console.log('OK:', name); };
let browser;
(async () => {
  const fixtures = JSON.parse(service('product-service', `
import json,sys
from app.database import SessionLocal
from app.models import Category, Product
with SessionLocal() as db:
 c=Category(name=sys.argv[1]);db.add(c);db.flush()
 p=Product(name=sys.argv[1]+' disponible',description='<img src=x onerror=alert(1)>',price=12.30,stock=3,category_id=c.id,image_url='javascript:alert(1)')
 q=Product(name=sys.argv[1]+' agotado',price=9.00,stock=0,category_id=c.id)
 db.add_all([p,q]);db.commit()
 print(json.dumps({'category':c.id,'product':p.id}))
`, marker));
  browser = await chromium.launch({headless: true, channel: process.env.BROWSER_CHANNEL || 'msedge'});
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, baseURL: process.env.FRONTEND_URL || 'http://127.0.0.1:8080/'});
  const page = await context.newPage();
  const jsErrors = [];
  page.on('pageerror', error => jsErrors.push(error.message));
  await page.goto(process.env.FRONTEND_URL || 'http://127.0.0.1:8080/');
  const visible = selector => page.locator(selector).waitFor({state: 'visible'});
  const search = async (name, available = false) => {
    await page.locator('#search').fill(name);
    await page.locator('#available').setChecked(available);
    const response = page.waitForResponse(r => r.url().includes('/api/products/?'));
    await page.getByRole('button', {name: 'Buscar', exact: true}).click(); await response;
    await page.waitForFunction(() => document.getElementById('products').getAttribute('aria-busy') === 'false');
  };
  await check('real catalog search, category and availability filters', async () => {
    await page.waitForFunction(id => [...document.querySelector('#category').options].some(o => o.value === String(id)), fixtures.category);
    await page.locator('#category').selectOption(String(fixtures.category));
    await search(marker); assert.equal(await page.locator('.product-card').count(), 2);
    await search(marker, true); assert.equal(await page.locator('.product-card').count(), 1);
    assert.match(await page.locator('.product-card').innerText(), /12,30/);
  });
  await check('real product detail renders untrusted description as text and rejects unsafe image URL', async () => {
    await page.getByRole('link', {name: 'Ver producto', exact: true}).click(); await visible('#detail');
    assert.equal(await page.locator('#detail-description').textContent(), '<img src=x onerror=alert(1)>');
    assert.equal(await page.locator('#detail-description img').count(), 0);
    assert.equal(await page.locator('#detail-image img').count(), 0);
    assert.match(await page.locator('#detail-stock').innerText(), /3/);
  });
  await check('catalog empty state is distinct from service failure', async () => {
    await page.getByRole('link', {name: 'Volver al catálogo'}).click();
    await search(marker + '-missing'); assert.equal(await page.locator('.product-card').count(), 0);
    assert.match(await page.locator('#catalog-status').textContent(), /No encontramos/);
    assert.equal(await page.locator('#catalog-error').isVisible(), false);
  });
  await check('injected 503 shows retry and recovery uses real catalog', async () => {
    await page.route('**/api/products/?**', route => route.fulfill({status: 503, contentType: 'application/json', body: '{}'}));
    await search(marker); await visible('#retry-catalog'); assert.match(await page.locator('#catalog-error').textContent(), /no está disponible/);
    await page.unroute('**/api/products/?**'); await page.locator('#retry-catalog').click();
    await page.waitForFunction(() => document.querySelectorAll('.product-card').length === 2);
  });
  await page.getByRole('link', {name: 'Iniciar sesión', exact: true}).click();
  await page.locator('#register-tab').click();
  const fillRegister = async pass => {
    await page.locator('#register-name').fill(marker);
    await page.locator('#register-email').fill(email);
    await page.locator('#register-password').fill(pass);
    await page.locator('#confirm-password').fill(pass);
  };
  await check('UTF-8 password byte limit prevents request', async () => {
    let sent = 0; const listener = request => {if (request.url().endsWith('/api/auth/register')) sent++;};
    page.on('request', listener); await fillRegister('é'.repeat(37));
    await page.locator('#register-form button').click(); await visible('#register-error');
    assert.match(await page.locator('#register-error').textContent(), /72 bytes/); assert.equal(sent, 0); page.off('request', listener);
  });
  await check('real registration succeeds without pretending to log in', async () => {
    await fillRegister(password); await page.locator('#register-form button').click();
    await page.waitForFunction(() => document.querySelector('#account-status').textContent.includes('Cuenta creada'));
    assert.equal(await page.locator('#profile').isVisible(), false);
  });
  await check('duplicate registration surfaces backend error', async () => {
    await page.locator('#register-tab').click(); await fillRegister(password); await page.locator('#register-form button').click();
    await visible('#register-error'); assert.match(await page.locator('#register-error').textContent(), /registrado/);
  });
  await page.locator('#login-tab').click(); await page.locator('#login-email').fill(email);
  await check('incorrect login remains signed out', async () => {
    await page.locator('#login-password').fill('incorrect-password'); await page.locator('#login-form button').click();
    await visible('#login-error'); assert.match(await page.locator('#login-error').textContent(), /incorrectos/);
    assert.equal(await page.locator('#profile').isVisible(), false);
  });
  const login = async () => {
    await page.locator('#login-email').fill(email); await page.locator('#login-password').fill(password);
    await page.locator('#login-form button').click(); await visible('#profile');
  };
  await check('real login verifies authenticated user and avoids persistent token storage', async () => {
    await login(); assert.equal(await page.locator('#profile-email').textContent(), email);
    assert.deepEqual(await page.evaluate(() => ({local: localStorage.length, session: sessionStorage.length, cookie: document.cookie})), {local: 0, session: 0, cookie: ''});
    assert.equal(await page.locator('#login-password').inputValue(), '');
  });
  await check('reload clears in-memory session; explicit logout clears account view', async () => {
    await page.reload(); await visible('#login-form'); assert.equal(await page.locator('#profile').isVisible(), false);
    await login(); await page.locator('#logout').click(); assert.equal(await page.locator('#profile').isVisible(), false);
    assert.equal(await page.locator('#profile-email').textContent(), '');
  });
  await check('injected expired session during user verification never shows authenticated profile', async () => {
    await page.route('**/api/users/me', route => route.fulfill({status: 401, contentType: 'application/json', body: '{"detail":"Token expirado"}'}));
    await page.locator('#login-email').fill(email); await page.locator('#login-password').fill(password);
    await page.locator('#login-form button').click(); await visible('#login-error');
    assert.equal(await page.locator('#profile').isVisible(), false); await page.unroute('**/api/users/me');
  });
  await check('frontend proxy preserves protected and internal gateway route restrictions', async () => {
    assert.equal((await page.request.get('/api/users/me')).status(), 401);
    assert.equal((await page.request.get('/api/orders/internal/test')).status(), 404);
    assert.equal((await page.request.get('/api/products/?limit=101')).status(), 422);
  });
  await page.getByRole('link', {name: 'Catálogo', exact: true}).click(); await search(marker, false);
  fs.mkdirSync('docs/frontend', {recursive: true});
  await page.screenshot({path: 'docs/frontend/catalogo-desktop.png', fullPage: true});
  await check('mobile catalog and access fit a 390px viewport', async () => {
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({path: 'docs/frontend/catalogo-mobile.png', fullPage: true});
    await page.getByRole('link', {name: 'Iniciar sesión', exact: true}).click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({path: 'docs/frontend/acceso-mobile.png', fullPage: true});
  });
  assert.deepEqual(jsErrors, []); report.status = 'passed';
})().catch(error => {report.status = 'failed'; console.error(error.message); process.exitCode = 1;}).finally(async () => {
  if (browser) await browser.close();
  try {
    service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product, Category
with SessionLocal() as db:
 db.query(Product).filter(Product.name.in_([sys.argv[1]+' disponible',sys.argv[1]+' agotado'])).delete(synchronize_session=False)
 db.query(Category).filter(Category.name==sys.argv[1]).delete(synchronize_session=False);db.commit()
`, marker);
    service('user-service', `
import sys
from app.database import SeccionLocal
from app.models import User
with SeccionLocal() as db:
 db.query(User).filter(User.email==sys.argv[1]).delete(synchronize_session=False);db.commit()
`, email);
    report.cleanup = true;
  } catch { console.error('Fixture cleanup failed'); report.cleanup = false; process.exitCode = 1; }
  report.date = new Date().toISOString();
  report.sha256 = {};
  for (const file of ['frontend/app/index.html', 'frontend/app/app.js', 'frontend/app/commerce.js', 'frontend/app/payments.js', 'frontend/app/styles.css', 'frontend/nginx.conf', 'frontend/Dockerfile', 'compose.frontend.yml', 'tests/frontend_browser.cjs']) {
    report.sha256[file] = require('node:crypto').createHash('sha256').update(fs.readFileSync(file, 'utf8').replaceAll('\r\n', '\n')).digest('hex');
  }
  fs.mkdirSync('docs/frontend', {recursive: true});
  fs.writeFileSync('docs/frontend/integracion.json', JSON.stringify(report, null, 2) + '\n');
});
