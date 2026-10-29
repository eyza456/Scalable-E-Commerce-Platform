/* UI-only customer journey; direct SQL is limited to owned fixture setup,
 * read-only business verification and cleanup. No bank data or real charges. */
const {chromium} = require('playwright');
const axe = require('./browser-tools/node_modules/axe-core');
const {execFileSync} = require('node:child_process');
const {randomUUID, createHash} = require('node:crypto');
const fs = require('node:fs'), assert = require('node:assert/strict');
const marker = 'journey-' + randomUUID().replaceAll('-', '');
const name = 'Lámpara de mesa · Demo ' + marker.slice(-6), password = 'Ui-' + randomUUID();
let email = marker + '@example.com', browser, user, product;
const orders = [], report = {scope:'UI-only customer journey; automated axe, keyboard and reflow checks in local Edge',steps:[],audits:[],keyboard:[],layouts:[],cleanup:false};
const service = (name, code, ...args) => execFileSync('docker',['compose','exec','-T',name,'python','-c',code,...args.map(String)],{encoding:'utf8'}).trim();
const step = async (name, fn) => {await fn();report.steps.push(name);console.log('OK:',name);};
(async()=>{
  product = Number(service('product-service', `
import sys
from app.database import SessionLocal
from app.models import Product
with SessionLocal() as db:
 p=Product(name=sys.argv[1],description='Producto temporal de demostración; sin envíos ni cobros reales.',price=12.30,stock=5)
 db.add(p);db.commit();print(p.id)
`,name));
  browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'msedge'});
  report.browser=browser.version();report.axeVersion=axe.version;
  const base=process.env.FRONTEND_URL||'http://127.0.0.1:8080/';
  const context=await browser.newContext({baseURL:base,viewport:{width:1440,height:1000}});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const key=async selector=>{await page.locator(selector).focus();await page.keyboard.press('Enter');};
  const audit=async name=>{
    await page.evaluate(axe.source);
    const result=await page.evaluate(()=>axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa','best-practice']}}));
    const reduce=values=>values.map(v=>({id:v.id,impact:v.impact,help:v.help,helpUrl:v.helpUrl,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));
    report.audits.push({name,violations:reduce(result.violations),incomplete:reduce(result.incomplete),passedRules:result.passes.length});
    console.log('AUDIT:',name,'violations='+result.violations.length,'incomplete='+result.incomplete.length);
  };
  const layout=async(name,width)=>{await page.setViewportSize({width,height:900});const fits=await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth);report.layouts.push({name,width,fits});assert.ok(fits,name+': overflow');};
  fs.mkdirSync('docs/frontend/demo',{recursive:true});
  await page.goto(base);await page.waitForFunction(()=>document.querySelector('#products').getAttribute('aria-busy')==='false');
  await step('initial Tab exposes skip link and Enter reaches main',async()=>{
    await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>document.activeElement.classList.contains('skip')));
    await page.keyboard.press('Enter');assert.equal(await page.evaluate(()=>document.activeElement.id),'main');
    report.keyboard.push('first Tab -> skip link -> main');await audit('catalog guest');
  });
  await step('registration and login through visible forms',async()=>{
    await key('#account-link');await key('#register-tab');
    await page.locator('#register-name').fill('Cliente de demostración');await page.locator('#register-email').fill(email);
    await page.locator('#register-password').fill(password);await page.locator('#confirm-password').fill(password);await audit('registration');
    const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/api/auth/register'));
    await key('#register-form button');user=(await(await response).json()).id;
    await page.waitForFunction(()=>document.querySelector('#account-status').textContent.includes('Cuenta creada'));
    await page.locator('#login-password').fill(password);await key('#login-form button');await page.locator('#profile').waitFor({state:'visible'});await audit('account signed in');
  });
  const add=async()=>{
    await page.getByRole('link',{name:'Catálogo',exact:true}).click();await page.locator('#search').fill(name);await key('#filters button[type=submit]');
    await page.waitForFunction(()=>document.querySelectorAll('.product-card').length===1&&document.querySelector('#products').getAttribute('aria-busy')==='false');
    await key('.product-card .button');await page.locator('#detail').waitFor({state:'visible'});await key('#add-button');
    await page.waitForFunction(()=>document.querySelector('#add-status').textContent.includes('agregado'));
    await page.getByRole('link',{name:'Ver mi carrito',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#cart-items').getAttribute('aria-busy')==='false');
  };
  const createOrder=async()=>{
    await page.getByRole('link',{name:'Revisar pedido',exact:true}).click();await page.waitForFunction(()=>!document.querySelector('#confirm-order').disabled);
    await key('#confirm-order');await page.locator('#order-result').waitFor({state:'visible'});
    const id=Number(await page.locator('#order-number').textContent());orders.push({id});
    await page.waitForFunction(()=>!document.querySelector('#payment-form').hidden&&!document.querySelector('#pay-button').disabled);return id;
  };
  let paidId;
  await step('catalog, detail, quantity update and checkout use real controls',async()=>{
    await add();await page.locator('.cart-controls input').fill('2');await key('.cart-controls button[type=submit]');
    await page.waitForFunction(()=>document.querySelector('#cart-total').textContent.includes('24,60')&&document.querySelector('#cart-items').getAttribute('aria-busy')==='false');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'update-cart-'+product);report.keyboard.push('cart update restores recreated control');
    await audit('cart');await page.screenshot({path:'docs/frontend/demo/carrito-desktop.png',fullPage:true});
    paidId=await createOrder();await audit('checkout payment ready');
  });
  await step('explicit simulated rejection then approval for one order',async()=>{
    await page.locator('#simulation-result').selectOption('insufficient_funds');await key('#pay-button');
    await page.waitForFunction(()=>document.querySelector('#payment-status').textContent.includes('fondos')&&!document.querySelector('#pay-button').disabled);
    await audit('payment rejected');assert.equal(await page.evaluate(()=>document.activeElement.id),'pay-button');
    await page.locator('#simulation-result').selectOption('approved');await key('#pay-button');
    await page.waitForFunction(()=>document.querySelector('#payment-status').textContent.includes('aprobado')&&!document.querySelector('#refresh-payment').disabled);
    assert.equal(await page.evaluate(()=>document.activeElement.id),'refresh-payment');report.keyboard.push('payment focus follows retry/status controls');
    await audit('payment approved');await page.screenshot({path:'docs/frontend/demo/pago-aprobado.png',fullPage:true});
  });
  await step('paid history blocks cancellation',async()=>{
    await page.getByRole('link',{name:'Mis pedidos',exact:true}).click();await page.getByRole('link',{name:'Ver pedido #'+paidId,exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#history-state').textContent==='Pagado');assert.equal(await page.locator('#cancel-order').isVisible(),false);await audit('paid history detail');
  });
  await step('second order cancellation supports Tab trap and Escape',async()=>{
    await add();const id=await createOrder();await page.getByRole('link',{name:'Mis pedidos',exact:true}).click();await page.getByRole('link',{name:'Ver pedido #'+id,exact:true}).click();
    await page.locator('#history-detail').waitFor({state:'visible'});await key('#cancel-order');assert.equal(await page.evaluate(()=>document.activeElement.id),'keep-order');
    for(let n=0;n<4;n++){await page.keyboard.press('Tab');assert.ok(await page.evaluate(()=>Boolean(document.activeElement.closest('#cancel-dialog'))));}
    await audit('cancel confirmation dialog');await page.keyboard.press('Escape');assert.equal(await page.evaluate(()=>document.activeElement.id),'cancel-order');
    report.keyboard.push('dialog defaults to keep, traps Tab and restores trigger on Escape');
    await key('#cancel-order');await key('#confirm-cancel');
    await page.waitForFunction(()=>document.querySelector('#history-state').textContent==='Cancelado'&&!document.querySelector('#refresh-order').disabled);
    assert.equal(await page.evaluate(()=>document.activeElement.id),'history-state');await audit('cancelled history detail');
  });
  await step('profile edit preserves session and changed email login',async()=>{
    await key('#account-link');await key('#edit-profile');email=marker+'-updated@example.com';
    await page.locator('#edit-name').fill('Cliente de demostración actualizado');await page.locator('#edit-email').fill(email);await audit('profile editing');await key('#save-profile');
    await page.waitForFunction(()=>document.querySelector('#profile-status').textContent.includes('Perfil actualizado'));assert.equal(await page.evaluate(()=>document.activeElement.id),'edit-profile');
    report.keyboard.push('profile save restores edit trigger');
    await key('#logout');await page.locator('#login-email').fill(email);await page.locator('#login-password').fill(password);await key('#login-form button');
    await page.locator('#profile').waitFor({state:'visible'});assert.equal(await page.locator('#profile-email').textContent(),email);
  });
  await step('responsive reflow, focus, reduced motion and font fallback',async()=>{
    await page.getByRole('link',{name:'Catálogo',exact:true}).click();for(const width of [320,390,768,1440])await layout('catalog',width);
    await page.setViewportSize({width:390,height:900});await audit('catalog mobile');await page.screenshot({path:'docs/frontend/demo/catalogo-mobile.png',fullPage:true});
    await page.getByRole('link',{name:'Mis pedidos',exact:true}).click();await page.waitForFunction(()=>document.querySelector('#orders-list').getAttribute('aria-busy')==='false');
    for(const width of [320,390,768,1440])await layout('history',width);
    await page.setViewportSize({width:390,height:900});await audit('history mobile');await page.screenshot({path:'docs/frontend/demo/historial-mobile.png',fullPage:true});
    await key('#account-link');await key('#edit-profile');for(const width of [320,390,768,1440])await layout('profile',width);
    await page.emulateMedia({reducedMotion:'reduce'});assert.ok(await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches));
    await page.locator('#edit-name').focus();assert.notEqual(await page.locator('#edit-name').evaluate(el=>getComputedStyle(el).outlineStyle),'none');report.keyboard.push('visible focus with reduced motion');
    const fallback=await context.newPage();await fallback.route(/fonts\.(googleapis|gstatic)\.com/,route=>route.abort());await fallback.goto(base);assert.ok(await fallback.locator('#catalog-title').isVisible());await fallback.close();
  });
  await step('injected catalog 503 is announced and recovers',async()=>{
    await page.getByRole('link',{name:'Catálogo',exact:true}).click();await page.route('**/api/products/?**',route=>route.fulfill({status:503,contentType:'application/json',body:'{}'}));
    await key('#filters button[type=submit]');await page.locator('#catalog-error').waitFor({state:'visible'});await audit('catalog unavailable');
    await page.unroute('**/api/products/?**');await key('#retry-catalog');await page.waitForFunction(()=>document.querySelector('#products').getAttribute('aria-busy')==='false');assert.equal(await page.locator('#catalog-error').isVisible(),false);
  });
  report.business=JSON.parse(service('payment-service', `
import sys,json
from sqlalchemy import text
from app.database import engine
with engine.connect() as db:
 p={'id':int(sys.argv[1])}
 print(json.dumps({'paid':db.execute(text("SELECT count(*) FROM payments WHERE order_id=:id AND status='PAID'"),p).scalar(),'rejected':db.execute(text("SELECT count(*) FROM payments WHERE order_id=:id AND status='REJECTED'"),p).scalar(),'events':db.execute(text('SELECT count(*) FROM outbox_events WHERE aggregate_id=:id'),p).scalar()}))
`,paidId));assert.deepEqual(report.business,{paid:1,rejected:1,events:3});
  report.remainingStock=Number(service('product-service','import sys;from app.database import SessionLocal;from app.models import Product;db=SessionLocal();print(db.get(Product,int(sys.argv[1])).stock);db.close()',product));assert.equal(report.remainingStock,3);
  assert.deepEqual(errors,[]);report.jsErrors=errors;
  assert.ok(report.audits.every(a=>a.violations.length===0),'Accessibility violations found; inspect report');report.status='passed';
})().catch(error=>{report.status='failed';console.error(error.message);process.exitCode=1;}).finally(async()=>{
  if(browser)await browser.close();
  try{
    if(user){
      service('payment-service', `
import sys,time
from sqlalchemy import text
from app.database import engine
deadline=time.monotonic()+40
with engine.connect() as db:
 while db.execute(text("SELECT count(*) FROM outbox_events WHERE payload->>'user_id'=:id AND published_at IS NULL"),{'id':sys.argv[1]}).scalar():
  db.rollback();assert time.monotonic()<deadline;time.sleep(.25)
`,user);
      service('product-service', `
import sys,time
from sqlalchemy import text
from app.database import engine
deadline=time.monotonic()+40
with engine.connect() as db:
 while db.execute(text("SELECT count(*) FROM inventory_reservations WHERE user_id=:id AND status='RESERVED'"),{'id':int(sys.argv[1])}).scalar():
  db.rollback();assert time.monotonic()<deadline;time.sleep(.25)
`,user);
      const actualEmail=service('user-service','import sys;from app.database import SeccionLocal;from app.models import User;db=SeccionLocal();print(db.get(User,int(sys.argv[1])).email);db.close()',user);assert.ok(actualEmail.startsWith(marker));
      execFileSync('python',['-c','import sys,json;sys.path.insert(0,"tests");from smoke_inventory import cleanup;cleanup(json.loads(sys.argv[1]),json.loads(sys.argv[2]),json.loads(sys.argv[3]))',JSON.stringify({id:user,email:actualEmail}),JSON.stringify({id:product,name}),JSON.stringify(orders)],{stdio:['ignore','pipe','pipe']});
    }else if(product)service('product-service','import sys;from app.database import SessionLocal;from app.models import Product;db=SessionLocal();db.query(Product).filter(Product.id==int(sys.argv[1]),Product.name==sys.argv[2]).delete(synchronize_session=False);db.commit();db.close()',product,name);
    report.cleanup=true;
  }catch{report.cleanup=false;console.error('Owned fixture cleanup failed');process.exitCode=1;}
  report.date=new Date().toISOString();report.sha256={};
  for(const file of ['frontend/app/index.html','frontend/app/app.js','frontend/app/commerce.js','frontend/app/payments.js','frontend/app/orders.js','frontend/app/profile.js','frontend/app/styles.css','tests/frontend_journey.cjs','tests/browser-tools/package-lock.json'])report.sha256[file]=createHash('sha256').update(fs.readFileSync(file,'utf8').replaceAll('\r\n','\n')).digest('hex');
  fs.mkdirSync('docs/frontend',{recursive:true});fs.writeFileSync('docs/frontend/recorrido-accesibilidad.json',JSON.stringify(report,null,2)+'\n');
});
