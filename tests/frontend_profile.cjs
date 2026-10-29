const {chromium} = require('playwright');
const {execFileSync} = require('node:child_process');
const {randomUUID, createHash} = require('node:crypto');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const marker = 'profile-ui-' + randomUUID().replaceAll('-', '');
const password = 'Ui-' + randomUUID(), originalEmail = marker + '@example.com';
const report = {scope: 'real profile updates/session refresh; transport errors and late responses explicitly injected', checks: [], cleanup: false};
const users = []; let browser, activeEmail = originalEmail;
const service = (name, code, ...args) => execFileSync('docker', ['compose', 'exec', '-T', name, 'python', '-c', code, ...args.map(String)], {encoding: 'utf8'}).trim();
const check = async (name, fn) => {await fn(); report.checks.push(name); console.log('OK:', name);};
(async () => {
  browser = await chromium.launch({headless: true, channel: process.env.BROWSER_CHANNEL || 'msedge'});
  const base = process.env.FRONTEND_URL || 'http://127.0.0.1:8080/';
  const context = await browser.newContext({baseURL: base, viewport: {width: 1440, height: 1000}});
  const page = await context.newPage(), errors = []; page.on('pageerror', error => errors.push(error.message));
  for (const email of [originalEmail, marker + '-other@example.com']) {
    const response = await page.request.post('/api/auth/register', {data: {name: marker, email, password}});
    assert.equal(response.status(), 201); users.push(await response.json());
  }
  const login = async email => {
    await page.goto(base + '#cuenta'); await page.reload();
    await page.locator('#login-email').fill(email); await page.locator('#login-password').fill(password);
    await page.locator('#login-form button').click(); await page.locator('#profile').waitFor({state: 'visible'});
  };
  const edit = async () => {await page.locator('#edit-profile').click(); await page.locator('#profile-form').waitFor({state: 'visible'});};
  const save = () => page.locator('#save-profile').click();
  await check('guest sees no editable profile', async () => {
    await page.goto(base + '#cuenta'); assert.equal(await page.locator('#profile').isVisible(), false);
    assert.equal(await page.locator('#profile-form').isVisible(), false);
  });
  await login(activeEmail);
  await check('edit preloads profile and discard causes no PUT', async () => {
    let puts = 0; const listener = req => {if (req.method() === 'PUT' && req.url().endsWith('/api/users/me')) puts++;};
    page.on('request', listener); await edit(); assert.equal(await page.locator('#edit-email').inputValue(), activeEmail);
    await page.locator('#edit-name').fill('Uncommitted changes'); await page.locator('#discard-profile').click();
    assert.equal(puts, 0); assert.equal(await page.locator('#profile-name').textContent(), marker); page.off('request', listener);
  });
  await check('unchanged values and trimmed short name do not submit', async () => {
    let puts = 0; const listener = req => {if (req.method() === 'PUT' && req.url().endsWith('/api/users/me')) puts++;};
    page.on('request', listener); await edit(); await save(); assert.match(await page.locator('#profile-status').textContent(), /No hay cambios/);
    await page.locator('#edit-name').fill('   '); await save(); assert.match(await page.locator('#profile-error').textContent(), /nombre/);
    assert.equal(puts, 0); page.off('request', listener); await page.locator('#discard-profile').click();
  });
  await check('duplicate email preserves existing account and session', async () => {
    await edit(); await page.locator('#edit-name').fill('Must not persist'); await page.locator('#edit-email').fill(users[1].email);
    await save(); await page.locator('#profile-error').waitFor({state: 'visible'});
    assert.match(await page.locator('#profile-error').textContent(), /registrado/);
    assert.equal(await page.locator('#profile-name').textContent(), marker); assert.equal(await page.locator('#profile-email').textContent(), originalEmail);
    await page.locator('#discard-profile').click();
  });
  await check('successful name/email update uses returned token on subsequent protected request', async () => {
    activeEmail = marker + '-updated@example.com'; await edit();
    await page.locator('#edit-name').fill('Perfil actualizado'); await page.locator('#edit-email').fill(activeEmail);
    const updated = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().endsWith('/api/users/me'));
    await save(); const value = await (await updated).json();
    await page.waitForFunction(() => document.querySelector('#profile-status').textContent.includes('Perfil actualizado'));
    assert.equal(await page.locator('#profile-email').textContent(), activeEmail);
    assert.equal(await page.locator('#profile-name').textContent(), 'Perfil actualizado');
    const request = page.waitForRequest(r => r.url().endsWith('/api/cart') && r.method() === 'GET');
    await page.locator('#cart-link').click();
    assert.equal((await request).headers().authorization, 'Bearer ' + value.access_token);
    assert.deepEqual(await page.evaluate(() => [localStorage.length, sessionStorage.length]), [0, 0]);
    await page.locator('#account-link').click();
    fs.mkdirSync('docs/frontend', {recursive: true}); await page.screenshot({path: 'docs/frontend/perfil-desktop.png', fullPage: true});
  });
  await check('future login rejects previous email and accepts changed email', async () => {
    assert.equal((await page.request.post('/api/auth/login', {data: {email: originalEmail, password}})).status(), 401);
    await login(activeEmail); assert.equal(await page.locator('#profile-email').textContent(), activeEmail);
  });
  await check('lost update acknowledgement signs out without automatically repeating PUT', async () => {
    const next = marker + '-lost@example.com'; await edit(); await page.locator('#edit-email').fill(next); let puts = 0;
    await page.route('**/api/users/me', async route => {
      if (route.request().method() === 'PUT') {puts++; await route.fetch(); await route.abort('failed');}
      else await route.continue();
    });
    await save(); await page.locator('#login-form').waitFor({state: 'visible'});
    assert.equal(puts, 1); assert.match(await page.locator('#account-status').textContent(), /No se confirmó/);
    assert.equal(await page.locator('#profile-name').textContent(), ''); await page.unroute('**/api/users/me');
    activeEmail = next; await login(activeEmail); assert.equal(await page.locator('#profile-email').textContent(), next);
  });
  await check('expired update session clears private form fields', async () => {
    await edit(); await page.locator('#edit-name').fill('Expired request');
    await page.route('**/api/users/me', route => route.request().method() === 'PUT'
      ? route.fulfill({status: 401, contentType: 'application/json', body: '{"detail":"Token expirado"}'}) : route.continue());
    await save(); await page.locator('#login-form').waitFor({state: 'visible'});
    assert.equal(await page.locator('#edit-name').inputValue(), ''); assert.equal(await page.locator('#edit-email').inputValue(), '');
    await page.unroute('**/api/users/me'); await login(activeEmail);
  });
  await check('late response after logout cannot replace another logged-in account', async () => {
    await edit(); await page.locator('#edit-name').fill('Late owner response');
    let release, reached;
    const held = new Promise(resolve => {release = resolve;});
    const fetched = new Promise(resolve => {reached = resolve;});
    await page.route('**/api/users/me', async route => {
      if (route.request().method() === 'PUT') {const response = await route.fetch(); reached(); await held; await route.fulfill({response});}
      else await route.continue();
    });
    await save(); await fetched; await page.locator('#logout').click();
    await page.locator('#login-email').fill(users[1].email); await page.locator('#login-password').fill(password);
    await page.locator('#login-form button').click(); await page.locator('#profile').waitFor({state: 'visible'});
    const response = page.waitForResponse(r => r.request().method() === 'PUT' && r.url().endsWith('/api/users/me'));
    release(); await response;
    await page.locator('#profile-status').evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await page.locator('#profile-email').textContent(), users[1].email);
    assert.equal(await page.locator('#profile-name').textContent(), marker); await page.unroute('**/api/users/me');
  });
  await check('mobile profile editing fits and only name/email are editable', async () => {
    await page.setViewportSize({width: 390, height: 844}); await edit();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.equal(await page.locator('#profile-form input').count(), 2);
    await page.screenshot({path: 'docs/frontend/perfil-mobile.png', fullPage: true});
  });
  assert.deepEqual(errors, []); report.status = 'passed';
})().catch(error => {report.status = 'failed'; console.error(error.message); process.exitCode = 1;}).finally(async () => {
  if (browser) await browser.close();
  try {
    for (const user of users) {
      service('cart-service', 'import sys;from app.redis_client import redis_client;redis_client.delete("cart:"+sys.argv[1])', user.id);
      service('user-service', `
import sys
from app.database import SeccionLocal
from app.models import User
with SeccionLocal() as db: db.query(User).filter(User.id==int(sys.argv[1])).delete(synchronize_session=False);db.commit()
`, user.id);
    }
    report.cleanup = true;
  } catch {report.cleanup = false; console.error('Owned fixture cleanup failed'); process.exitCode = 1;}
  report.date = new Date().toISOString(); report.sha256 = {};
  for (const file of ['frontend/app/profile.js', 'frontend/app/app.js', 'frontend/app/index.html', 'frontend/app/styles.css', 'tests/frontend_profile.cjs']) report.sha256[file] = createHash('sha256').update(fs.readFileSync(file, 'utf8').replaceAll('\r\n', '\n')).digest('hex');
  fs.mkdirSync('docs/frontend', {recursive: true}); fs.writeFileSync('docs/frontend/perfil.json', JSON.stringify(report, null, 2) + '\n');
});
