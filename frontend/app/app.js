'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = {token: null, user: null, page: 0, size: 12, catalogRequest: 0, detailRequest: 0};
  let catalogController, detailController;
  const money = value => new Intl.NumberFormat('es-BO', {minimumFractionDigits: 2, maximumFractionDigits: 2}).format(Number(value));

  class ApiError extends Error {
    constructor(message, status = 0, detail = null) { super(message); this.status = status; this.detail = detail; }
  }
  async function api(path, {method = 'GET', body, authenticated = false, signal, headers: extraHeaders = {}} = {}) {
    const requestToken = state.token;
    const controller = new AbortController();
    const cancel = () => controller.abort();
    if (signal?.aborted) controller.abort();
    else signal?.addEventListener('abort', cancel, {once: true});
    const timeout = setTimeout(cancel, 15000);
    try {
      const headers = {Accept: 'application/json', ...extraHeaders};
      if (body !== undefined) headers['Content-Type'] = 'application/json';
      if (authenticated && requestToken) headers.Authorization = `Bearer ${requestToken}`;
      const response = await fetch(`/api${path}`, {
        method, headers, signal: controller.signal, cache: 'no-store', credentials: 'omit',
        body: body === undefined ? undefined : JSON.stringify(body)
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        if (response.status === 401 && authenticated && requestToken === state.token) {
          state.token = null; state.user = null; syncAccount();
        }
        let message = 'No se pudo completar la solicitud. Inténtalo más tarde.';
        if (typeof data?.detail === 'string') message = data.detail;
        if (typeof data?.detail?.message === 'string') message = data.detail.message;
        if (response.status === 422) message = 'Revisa los datos ingresados y sus límites.';
        if (response.status >= 500) message = 'El servicio no está disponible. Inténtalo más tarde.';
        throw new ApiError(message, response.status, data?.detail);
      }
      if (data === null) throw new ApiError('La respuesta del servicio no es válida.');
      return data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (signal?.aborted) throw error;
      throw new ApiError(method === 'GET'
        ? 'No se pudo conectar. Comprueba tu conexión y vuelve a intentarlo.'
        : 'No se confirmó el resultado. Comprueba tu conexión antes de volver a intentarlo.');
    } finally {
      clearTimeout(timeout); signal?.removeEventListener('abort', cancel);
    }
  }
  function feedback(id, message = '') { $(id).textContent = message; $(id).hidden = !message; }
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  const commerce = window.NexoCommerce({api, state, $, feedback, element, money});
  const orders = window.NexoOrders({api, state, $, feedback, element, money});
  function imageFor(product) {
    const box = element('div', undefined, 'product-image');
    const fallback = () => box.replaceChildren(element('span', 'Nexo', 'image-placeholder'));
    let url;
    try { url = new URL(product.image_url); } catch { fallback(); return box; }
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) { fallback(); return box; }
    const img = document.createElement('img');
    img.alt = product.name; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
    img.addEventListener('error', fallback, {once: true}); img.src = url.href; box.append(img);
    return box;
  }
  function productCard(product) {
    const card = element('article', undefined, 'product-card');
    const body = element('div', undefined, 'product-content');
    const title = element('h2'); const link = element('a', product.name);
    link.href = `#producto/${product.id}`; title.append(link);
    body.append(element('span', product.category || 'Sin categoría', 'eyebrow'), title,
      element('p', `Bs ${money(product.price)}`, 'price'),
      element('p', product.is_active && product.stock > 0 ? `${product.stock} disponibles` : 'No disponible', 'stock'));
    const more = element('a', 'Ver producto', 'button'); more.href = link.href; body.append(more);
    card.append(imageFor(product), body); return card;
  }
  async function loadCatalog() {
    catalogController?.abort(); catalogController = new AbortController();
    const version = ++state.catalogRequest;
    const query = new URLSearchParams({skip: String(state.page * state.size), limit: String(state.size + 1)});
    const name = $('search').value.trim();
    if (name) query.set('name', name);
    if ($('category').value) query.set('category_id', $('category').value);
    if ($('available').checked) query.set('available', 'true');
    $('products').replaceChildren(); $('products').setAttribute('aria-busy', 'true');
    $('catalog-status').textContent = 'Cargando productos…';
    feedback('catalog-error'); $('retry-catalog').hidden = true;
    $('previous').disabled = true; $('next').disabled = true;
    try {
      const products = await api(`/products/?${query}`, {signal: catalogController.signal});
      if (version !== state.catalogRequest) return;
      if (!Array.isArray(products)) throw new ApiError('La respuesta del catálogo no es válida.');
      const visible = products.slice(0, state.size);
      $('products').replaceChildren(...visible.map(productCard));
      $('catalog-status').textContent = visible.length ? `${visible.length} productos en esta página` : 'No encontramos productos con estos filtros.';
      $('previous').disabled = state.page === 0; $('next').disabled = products.length <= state.size;
      $('page-label').textContent = `Página ${state.page + 1}`;
    } catch (error) {
      if (version !== state.catalogRequest) return;
      $('catalog-status').textContent = 'No se pudo cargar el catálogo.';
      feedback('catalog-error', error.message); $('retry-catalog').hidden = false;
    } finally {
      if (version === state.catalogRequest) $('products').setAttribute('aria-busy', 'false');
    }
  }
  async function loadCategories() {
    try {
      const categories = []; let page = 0;
      while (true) {
        const batch = await api(`/categories?skip=${page * 100}&limit=100`);
        if (!Array.isArray(batch)) throw new ApiError('Categorías no disponibles.');
        categories.push(...batch); if (batch.length < 100) break; page++;
      }
      for (const c of categories) {
        const option = element('option', c.name); option.value = String(c.id); $('category').append(option);
      }
    } catch {
      $('category-status').textContent = 'No se pudieron cargar las categorías. Puedes buscar por nombre.';
    }
  }
  async function loadDetail(id) {
    detailController?.abort(); detailController = new AbortController();
    const version = ++state.detailRequest;
    $('detail').hidden = true; $('detail-status').textContent = 'Cargando producto…'; feedback('detail-error');
    try {
      const product = await api(`/products/${id}`, {signal: detailController.signal});
      if (version !== state.detailRequest) return;
      $('detail-title').textContent = product.name;
      $('detail-price').textContent = `Bs ${money(product.price)}`;
      $('detail-category').textContent = product.category || 'Sin categoría';
      $('detail-description').textContent = product.description || 'Este producto no tiene descripción.';
      $('detail-stock').textContent = product.is_active && product.stock > 0 ? `${product.stock} unidades disponibles` : 'Producto no disponible';
      $('detail-image').replaceChildren(imageFor(product)); $('detail').hidden = false; $('detail-status').textContent = '';
      commerce.product(product);
    } catch (error) {
      if (version !== state.detailRequest) return;
      $('detail-status').textContent = ''; feedback('detail-error', error.status === 404 ? 'No encontramos este producto.' : error.message);
    }
  }
  function syncAccount() {
    const signed = Boolean(state.user && state.token);
    $('account-link').textContent = signed ? 'Mi cuenta' : 'Iniciar sesión'; $('logout').hidden = !signed;
    $('profile').hidden = !signed; document.querySelector('.tabs').hidden = signed;
    $('login-form').hidden = signed || $('register-tab').getAttribute('aria-pressed') === 'true';
    $('register-form').hidden = signed || $('login-tab').getAttribute('aria-pressed') === 'true';
    $('profile-name').textContent = signed ? state.user.name : '';
    $('profile-email').textContent = signed ? state.user.email : '';
    commerce.session(signed ? state.user.id : null);
    orders.session(signed ? state.user.id : null);
  }
  function setMode(mode) {
    for (const tab of ['login', 'register']) $(tab + '-tab').setAttribute('aria-pressed', String(tab === mode));
    feedback('login-error'); feedback('register-error'); syncAccount();
  }
  function busy(form, working) {
    for (const control of form.elements) control.disabled = working;
    $('login-tab').disabled = working; $('register-tab').disabled = working;
    form.setAttribute('aria-busy', String(working));
  }
  $('login-form').addEventListener('submit', async event => {
    event.preventDefault(); const form = event.currentTarget;
    const password = $('login-password').value;
    feedback('login-error'); feedback('account-status');
    if (new TextEncoder().encode(password).length > 72) { feedback('login-error', 'La contraseña supera el máximo de 72 bytes.'); return; }
    busy(form, true);
    let candidate;
    try {
      const result = await api('/auth/login', {method: 'POST', body: {email: $('login-email').value.trim(), password}});
      if (typeof result.access_token !== 'string' || !result.access_token) throw new ApiError('No se recibió una sesión válida.');
      candidate = result.access_token; state.token = candidate;
      state.user = await api('/users/me', {authenticated: true});
      form.reset(); syncAccount(); feedback('account-status', 'Sesión iniciada.');
    } catch (error) {
      if (candidate === state.token) {state.token = null; state.user = null; syncAccount();}
      feedback('login-error', error.status === 401
        ? (candidate ? 'No se pudo verificar la sesión. Inicia sesión de nuevo.' : 'Correo o contraseña incorrectos.')
        : error.message);
    } finally { busy(form, false); $('login-password').value = ''; }
  });
  $('register-form').addEventListener('submit', async event => {
    event.preventDefault(); const form = event.currentTarget;
    feedback('register-error'); feedback('account-status');
    const password = $('register-password').value;
    if (password !== $('confirm-password').value) { feedback('register-error', 'Las contraseñas no coinciden.'); return; }
    if (new TextEncoder().encode(password).length > 72) { feedback('register-error', 'La contraseña supera el máximo de 72 bytes.'); return; }
    const name = $('register-name').value.trim(), email = $('register-email').value.trim();
    if (name.length < 3) { feedback('register-error', 'Escribe un nombre de al menos 3 caracteres.'); return; }
    busy(form, true);
    try {
      await api('/auth/register', {method: 'POST', body: {name, email, password}});
      form.reset(); setMode('login'); $('login-email').value = email;
      feedback('account-status', 'Cuenta creada. Inicia sesión con tu correo y contraseña.'); $('login-password').focus();
    } catch (error) { feedback('register-error', error.message); }
    finally {busy(form, false); $('register-password').value = ''; $('confirm-password').value = '';}
  });
  $('logout').addEventListener('click', () => {
    state.token = null; state.user = null; $('login-form').reset(); $('register-form').reset();
    setMode('login'); feedback('account-status', 'Sesión cerrada en esta página.'); location.hash = '#cuenta';
  });
  $('login-tab').addEventListener('click', () => {setMode('login'); feedback('account-status');});
  $('register-tab').addEventListener('click', () => {setMode('register'); feedback('account-status');});
  $('filters').addEventListener('submit', event => {event.preventDefault(); state.page = 0; loadCatalog();});
  $('reset-filters').addEventListener('click', () => {$('filters').reset(); state.page = 0; loadCatalog();});
  $('retry-catalog').addEventListener('click', loadCatalog);
  $('previous').addEventListener('click', () => {if (state.page > 0) {state.page--; loadCatalog();}});
  $('next').addEventListener('click', () => {state.page++; loadCatalog();});
  function route() {
    const hash = location.hash || '#catalogo';
    const match = /^#producto\/([1-9]\d*)$/.exec(hash);
    const orderMatch = /^#pedidos\/([1-9]\d*)$/.exec(hash);
    const view = match ? 'detail' : hash === '#pedidos' || orderMatch ? 'orders' : hash === '#cuenta' ? 'account' : hash === '#carrito' ? 'cart' : hash === '#checkout' ? 'checkout' : 'catalog';
    for (const name of ['catalog', 'account', 'detail', 'cart', 'checkout', 'orders']) $(name + '-view').hidden = name !== view;
    const titles = {catalog: 'Catálogo', account: 'Mi cuenta', detail: 'Producto', cart: 'Carrito', checkout: 'Confirmar pedido', orders: 'Mis pedidos'};
    document.title = `Nexo · ${titles[view]}`;
    if (match) loadDetail(match[1]);
    else {detailController?.abort(); state.detailRequest++;}
    commerce.route(view);
    orders.route(view, orderMatch ? Number(orderMatch[1]) : null);
    $('main').focus({preventScroll: true}); window.scrollTo(0, 0);
  }
  window.addEventListener('hashchange', route);
  syncAccount(); route(); loadCategories(); loadCatalog();
})();
