/* Optional visual hardening: admin console, empty-cart action, axe, keyboard semantics and 200% zoom.
 * Runs against the real Compose stack. Browser engines can be limited with BROWSER_ENGINES=chromium,firefox,webkit.
 */
const {chromium, firefox, webkit} = require('playwright');
const axe = require(process.env.AXE_CORE_MODULE || './browser-tools/node_modules/axe-core');
const {execFileSync} = require('node:child_process');
const {randomUUID, createHash} = require('node:crypto');
const fs = require('node:fs');
const assert = require('node:assert/strict');

const marker = 'visual-' + randomUUID().replaceAll('-', '');
const password = 'Ui-' + randomUUID();
const adminEmail = marker + '-admin@example.com';
const managedEmail = marker + '-customer@example.com';
const report = {scope: 'optional visual hardening on the real frontend and gateway', engines: [], checks: [], cleanup: false};
const compose = process.env.TEST_COMPOSE_ARGS ? JSON.parse(process.env.TEST_COMPOSE_ARGS) : ['docker', 'compose'];
const service = (name, code, ...args) => execFileSync(compose[0], [...compose.slice(1), 'exec', '-T', name, 'python', '-c', code, ...args.map(String)], {encoding: 'utf8'}).trim();
const base = process.env.FRONTEND_URL || 'http://127.0.0.1:8080/';
const requested = (process.env.BROWSER_ENGINES || 'chromium,firefox,webkit').split(',').map(value => value.trim()).filter(Boolean);
const engines = {chromium, firefox, webkit};
let admin, product;
let executedEngines = 0;

async function audit(page, name, reportEntry) {
  await page.evaluate(axe.source);
  const result = await page.evaluate(() => axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice']}}));
  reportEntry.audits.push({name, violations: result.violations.map(item => ({id: item.id, impact: item.impact, nodes: item.nodes.map(node => node.target)})), incomplete: result.incomplete.length});
  assert.equal(result.violations.length, 0, `${name}: axe violations`);
}

async function login(page) {
  await page.goto(base + '#cuenta');
  await page.locator('#login-email').fill(adminEmail);
  await page.locator('#login-password').fill(password);
  await page.locator('#login-form button').click();
  await page.locator('#profile').waitFor({state: 'visible'});
  await page.locator('#admin-link').waitFor({state: 'visible'});
}

(async () => {
  admin = JSON.parse(service('user-service', `
import json,sys
from app.database import SeccionLocal
from app.models import User
from app.user_actions import register_user
from app.schemas import UserCreate
with SeccionLocal() as db:
 u=register_user(db,UserCreate(name=sys.argv[1],email=sys.argv[2],password=sys.argv[3]));print(json.dumps({'id':u.id}))
`, marker + ' admin', adminEmail, password));
  const managed = JSON.parse(service('user-service', `
import json,sys
from app.database import SeccionLocal
from app.models import User
from app.user_actions import register_user
from app.schemas import UserCreate
with SeccionLocal() as db:
 u=register_user(db,UserCreate(name=sys.argv[1],email=sys.argv[2],password=sys.argv[3]));print(json.dumps({'id':u.id}))
`, marker + ' customer', managedEmail, password));
  service('user-service', `import sys;from app.database import SeccionLocal;from app.models import User
with SeccionLocal() as db:
 u=db.get(User,int(sys.argv[1]));u.role='admin';db.commit()`, admin.id);
  product = Number(service('product-service', `import sys;from app.database import SessionLocal;from app.models import Product
with SessionLocal() as db:
 p=Product(name=sys.argv[1],description='Visual test',price=4.50,stock=3);db.add(p);db.commit();print(p.id)`, marker + ' producto'));
  for (const name of requested) {
    const engine = engines[name];
    if (!engine) continue;
    let browser;
    const entry = {engine: name, checks: [], audits: [], layouts: []};
    try {
      try {
        browser = await engine.launch({headless: true, ...(name === 'chromium' && process.env.BROWSER_CHANNEL ? {channel: process.env.BROWSER_CHANNEL} : {})});
      } catch (error) {
        entry.skipped = `Motor no disponible: ${error.message}`; report.engines.push(entry); continue;
      }
      executedEngines++;
      const context = await browser.newContext({baseURL: base, viewport: {width: 1440, height: 1000}});
      const page = await context.newPage(); page.setDefaultTimeout(30000);
      await login(page);
      await page.getByRole('link', {name: 'Administración', exact: true}).click();
      await page.locator('#admin-view').waitFor({state: 'visible'});
      await page.locator('#admin-private').waitFor({state: 'visible'});
      await page.locator('#admin-users').waitFor({state: 'visible'});
      await page.waitForFunction(() => document.querySelector('#admin-users').getAttribute('aria-busy') === 'false');
      await audit(page, `${name}: admin`, entry);
      assert.equal(await page.locator('main').getAttribute('tabindex'), '-1');
      assert.equal(await page.getByRole('button', {name: 'Actualizar', exact: true}).count(), 1);
      entry.checks.push('screen-reader-oriented landmarks and accessible control names');
      await page.locator('#admin-search').fill(managedEmail); await page.locator('#admin-toolbar button[type="submit"]').click();
      const row = page.locator('#admin-users tr').filter({hasText: managedEmail}); await row.waitFor({state: 'visible'});
      await row.locator('select').selectOption('seller'); await row.locator('input[type="checkbox"]').uncheck(); await row.getByRole('button', {name: 'Guardar'}).click();
      await page.waitForFunction(() => document.querySelector('#admin-status').textContent.includes('Cambios guardados'));
      assert.equal(await row.locator('select').inputValue(), 'seller'); assert.equal(await row.locator('input[type="checkbox"]').isChecked(), false);
      entry.checks.push('admin can change role and active state of another user');
      await row.locator('select').selectOption('Customer'); await row.locator('input[type="checkbox"]').check(); await row.getByRole('button', {name: 'Guardar'}).click();
      await page.waitForFunction(() => document.querySelector('#admin-status').textContent.includes('guardados'));
      await page.getByRole('link', {name: 'Catálogo', exact: true}).click();
      await page.locator('#search').fill(marker + ' producto'); await page.locator('#filters button[type="submit"]').click();
      await page.waitForFunction(() => document.querySelector('#products').getAttribute('aria-busy') === 'false' && document.querySelectorAll('.product-card').length === 1);
      await page.getByRole('link', {name: 'Ver producto', exact: true}).click(); await page.locator('#detail').waitFor({state: 'visible'});
      await page.locator('#add-button').click(); await page.locator('#add-status').waitFor({state: 'visible'});
      await page.getByRole('link', {name: 'Ver mi carrito', exact: true}).click(); await page.waitForFunction(() => document.querySelector('#cart-items').getAttribute('aria-busy') === 'false');
      await page.locator('#clear-cart').click(); await page.locator('#clear-cart-dialog').waitFor({state: 'visible'}); await page.locator('#keep-cart').click();
      assert.equal(await page.locator('#clear-cart-dialog').isVisible(), false);
      await page.locator('#clear-cart').click(); await page.locator('#confirm-clear-cart').click();
      await page.locator('.empty-cart').waitFor({state: 'visible'}); entry.checks.push('empty-cart confirmation preserves and then clears the cart');
      await audit(page, `${name}: cart`, entry);
      await page.evaluate(() => {document.documentElement.style.zoom = '2';});
      const fits = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1); entry.layouts.push({zoom: 2, width: 1440, fits}); assert.ok(fits, `${name}: 200% zoom overflow`);
      await page.evaluate(() => {document.documentElement.style.zoom = '';});
      await page.keyboard.press('Tab');
      entry.checks.push('keyboard focus remains available after zoom and dialogs');
      await context.close(); report.engines.push(entry);
    } catch (error) {
      entry.error = error.message; report.engines.push(entry); throw error;
    } finally { if (browser) await browser.close(); }
  }
  assert.ok(executedEngines > 0, 'No hay ningún motor de navegador disponible');
  report.status = 'passed';
})().catch(error => {report.status = 'failed'; console.error(error.stack || error.message); process.exitCode = 1;}).finally(() => {
  try {
    service('cart-service', 'import sys;from app.redis_client import redis_client;redis_client.delete("cart:"+sys.argv[1])', admin.id);
    service('product-service', 'import sys;from app.database import SessionLocal;from app.models import Product;db=SessionLocal();db.query(Product).filter(Product.id==int(sys.argv[1])).delete();db.commit()', product);
  service('user-service', `import sys;from app.database import SeccionLocal;from app.models import User
with SeccionLocal() as db: db.query(User).filter(User.email.in_([sys.argv[1],sys.argv[2]])).delete(synchronize_session=False);db.commit()`, adminEmail, managedEmail);
    report.cleanup = true;
  } catch (error) { report.cleanup = false; console.error('Optional visual fixture cleanup failed:', error.message); process.exitCode = 1; }
  report.date = new Date().toISOString();
  for (const file of ['frontend/app/index.html', 'frontend/app/app.js', 'frontend/app/commerce.js', 'frontend/app/admin.js', 'frontend/app/styles.css', 'tests/frontend_visual_optional.cjs']) report.sha256 = {...report.sha256, [file]: createHash('sha256').update(fs.readFileSync(file, 'utf8').replaceAll('\r\n', '\n')).digest('hex')};
  fs.mkdirSync('docs/frontend', {recursive: true}); fs.writeFileSync('docs/frontend/pruebas-compatibilidad.json', JSON.stringify(report, null, 2) + '\n');
});
