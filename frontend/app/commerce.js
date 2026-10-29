'use strict';
// Cart and checkout own their state; authentication and catalog stay in app.js.
window.NexoCommerce = function ({api, state, $, feedback, element, money}) {
  let userId = null, epoch = 0, view = 'catalog', selectedProduct = null;
  let cart = null, order = null, checkoutId = null, phase = 'idle';
  let working = false, loading = false, uncertainCart = false, canResume = false;
  let timer, polls = 0, readVersion = 0;
  const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
  const signed = () => userId !== null && Boolean(state.token && state.user);
  const locked = () => working || loading || uncertainCart || Boolean(cart?.checkout_id) || ['pending', 'unknown', 'submitting'].includes(phase);
  const current = version => version === epoch && signed();
  const stopPolling = () => {clearTimeout(timer); timer = undefined;};

  function render() {
    for (const panel of ['cart-private', 'checkout-private']) $(panel).hidden = !signed();
    document.querySelectorAll('.session-needed').forEach(node => {node.hidden = signed();});
    $('cart-link').textContent = cart && signed() ? `Carrito (${cart.items.reduce((sum, item) => sum + item.quantity, 0)})` : 'Carrito';
    $('cart-items').setAttribute('aria-busy', String(loading || working));
    $('refresh-cart').disabled = working || loading;
    $('add-button').disabled = working || !selectedProduct?.is_active || selectedProduct.stock < 1 || (signed() && locked());
    $('add-quantity').disabled = $('add-button').disabled;
    $('cart-summary').hidden = !cart?.items.length || !signed();
    $('recover-checkout').hidden = !checkoutId || !signed();
    $('confirm-order').hidden = !signed() || !cart?.items.length || Boolean(checkoutId) || Boolean(order);
    $('confirm-order').disabled = locked() || phase === 'rejected';
    $('check-order').hidden = !checkoutId || Boolean(order) || !signed();
    $('check-order').disabled = working || loading;
    $('resume-order').hidden = !canResume || !signed();
    $('resume-order').disabled = working || loading;
    $('order-result').hidden = !order || !signed();
    if (order) {
      $('order-number').textContent = String(order.id);
      const labels = {PENDING: 'Pendiente de pago', PAID: 'Pagado', CANCELLED: 'Cancelado', CANCELLING: 'Cancelación en curso', PROCESSING: 'En preparación', SHIPPED: 'Enviado', DELIVERED: 'Entregado'};
      $('order-status').textContent = labels[order.status] || order.status;
    } else {
      $('order-number').textContent = ''; $('order-status').textContent = '';
    }
    $('cart-items').replaceChildren(); $('checkout-items').replaceChildren();
    if (cart) {
      if (!cart.items.length) $('cart-items').append(element('p', 'Tu carrito está vacío.', 'empty-cart'));
      for (const item of cart.items) $('cart-items').append(cartRow(item));
      $('cart-total').textContent = `Bs ${money(cart.total)}`;
    } else $('cart-total').textContent = '';
    const review = order || cart;
    for (const item of review?.items || []) {
      const row = element('div', undefined, 'review-row');
      row.append(element('span', `${item.product_name || item.name} × ${item.quantity}`), element('strong', `Bs ${money(item.subtotal)}`));
      $('checkout-items').append(row);
    }
    $('checkout-total').textContent = review ? `Total: Bs ${money(review.total)}` : '';
    if (cart?.checkout_id) $('cart-status').textContent = 'Este carrito tiene un pedido en curso. Consulta su resultado antes de modificarlo.';
  }
  function cartRow(item) {
    const row = element('article', undefined, 'cart-row');
    row.append(element('h2', item.name), element('p', `Bs ${money(item.price)} por unidad`));
    const form = element('form', undefined, 'cart-controls');
    const label = element('label', 'Cantidad'); const input = document.createElement('input');
    input.id = `quantity-${item.product_id}`; input.type = 'number'; input.min = '1'; input.max = '100'; input.required = true; input.value = String(item.quantity);
    label.htmlFor = input.id;
    const update = element('button', 'Actualizar', 'secondary'); update.type = 'submit';
    const remove = element('button', 'Quitar', 'secondary'); remove.type = 'button';
    for (const node of [input, update, remove]) node.disabled = locked();
    form.append(label, input, update, remove);
    form.addEventListener('submit', event => {
      event.preventDefault(); const quantity = Number(input.value);
      if (!Number.isInteger(quantity) || quantity < 1 || quantity > 100) return;
      mutate(`/cart/items/${item.product_id}`, 'PUT', {quantity}, 'Cantidad y precio actualizados.');
    });
    remove.addEventListener('click', () => mutate(`/cart/items/${item.product_id}`, 'DELETE', undefined, 'Producto eliminado.'));
    row.append(form, element('strong', `Subtotal: Bs ${money(item.subtotal)}`)); return row;
  }
  function resetCheckout() {
    stopPolling(); checkoutId = null; order = null; phase = 'idle'; canResume = false; polls = 0;
    feedback('checkout-error'); feedback('checkout-status');
  }
  async function loadCart(recover = true) {
    if (!signed()) return;
    const version = epoch, request = ++readVersion;
    loading = true; feedback('cart-error'); $('cart-status').textContent = 'Consultando carrito…'; render();
    try {
      const result = await api('/cart', {authenticated: true});
      if (!current(version) || request !== readVersion) return;
      cart = result; uncertainCart = false;
      $('cart-status').textContent = cart.items.length ? 'Carrito actualizado.' : '';
      if (recover) {
        const found = cart.checkout_id || (!cart.items.length ? cart.last_checkout_id : null);
        if (uuid(found) && found !== checkoutId) {checkoutId = found; order = null; phase = 'pending'; polls = 0;}
        if (checkoutId && !order) await lookup(version);
      }
    } catch (error) {
      if (!current(version) || request !== readVersion) return;
      cart = null; feedback('cart-error', error.message); $('cart-status').textContent = 'No se pudo cargar el carrito.';
    } finally {
      if (current(version) && request === readVersion) {loading = false; render();}
    }
  }
  async function mutate(path, method, body, message) {
    if (!signed()) {feedback('add-error', 'Inicia sesión antes de agregar productos.'); return;}
    if (locked()) return;
    const version = epoch; working = true; feedback('add-error'); feedback('cart-error'); render();
    try {
      await api(path, {method, body, authenticated: true});
      if (!current(version)) return;
      resetCheckout();
      feedback('add-status', message); $('cart-status').textContent = message;
      await loadCart();
    } catch (error) {
      if (!current(version)) return;
      uncertainCart = !error.status || error.status >= 500;
      const message = uncertainCart ? 'No se confirmó el cambio. Actualiza el carrito para comprobarlo; no se repetirá automáticamente.' : error.message;
      feedback('cart-error', message); feedback('add-error', message);
      if (uuid(error.detail?.checkout_id)) {checkoutId = error.detail.checkout_id; phase = 'pending';}
    } finally {if (current(version)) {working = false; render();}}
  }
  function schedule(version) {
    stopPolling();
    if (view !== 'checkout' || !current(version)) return;
    if (polls >= 10) {
      feedback('checkout-status', 'El pedido sigue en proceso. Puedes consultar el resultado manualmente sin crear otro.'); return;
    }
    timer = setTimeout(async () => {
      if (!current(version) || working || loading) return;
      polls++; working = true; render();
      try {await lookup(version);} finally {if (current(version)) {working = false; render();}}
    }, 2500);
  }
  async function accept(result, version) {
    if (!current(version)) return;
    if (result.id) {
      order = result; phase = 'complete'; canResume = false; stopPolling();
      feedback('checkout-error'); feedback('checkout-status', 'Tu pedido fue creado. Revisa el total confirmado por el servidor.');
      await loadCart(false);
    } else {
      phase = 'pending'; canResume = false;
      feedback('checkout-status', 'Tu pedido está en proceso. Consultaremos el resultado sin crear otro.'); schedule(version);
    }
  }
  async function lookup(version = epoch) {
    if (!checkoutId || !current(version)) return;
    try {
      const result = await api(`/orders/checkouts/${checkoutId}`, {authenticated: true});
      await accept(result, version);
    } catch (error) {
      if (!current(version)) return;
      stopPolling(); canResume = false;
      if (error.status === 409 && error.detail?.code) {
        phase = 'rejected'; checkoutId = null;
        feedback('checkout-error', error.message); feedback('checkout-status', 'El pedido no se creó. Vuelve al carrito, revisa los productos y actualiza las cantidades para confirmar el precio vigente.');
      } else if (error.status === 404 && cart?.items.length && cart.version !== checkoutId && !cart.checkout_id) {
        phase = 'rejected'; checkoutId = null;
        feedback('checkout-error', 'El carrito cambió en otra sesión. Revisa su contenido antes de confirmar de nuevo.');
        feedback('checkout-status', 'No se encontró un pedido para la versión anterior del carrito.');
      } else {
        phase = 'unknown'; canResume = error.status === 404 && cart?.version === checkoutId && !cart.checkout_id && cart.items.length > 0;
        feedback('checkout-error', error.status === 404 ? 'Aún no se encontró este intento. Puedes consultar de nuevo o reintentar con la misma referencia si el carrito no cambió.' : error.message);
        feedback('checkout-status', 'No se confirmó el resultado. No se creará otro pedido automáticamente.');
      }
    }
  }
  async function submitOrder(resume = false) {
    if (!signed() || working || loading || uncertainCart) return;
    if (resume ? !canResume : locked() || Boolean(checkoutId) || !cart?.items.length) return;
    if (!resume) checkoutId = cart.version;
    if (!uuid(checkoutId)) {feedback('checkout-error', 'Actualiza el carrito antes de confirmar.'); return;}
    const version = epoch;
    stopPolling(); working = true; phase = 'submitting'; canResume = false; render();
    feedback('checkout-error'); feedback('checkout-status', 'Confirmando tu pedido…');
    try {
      const result = await api('/orders', {method: 'POST', authenticated: true, headers: {'Idempotency-Key': checkoutId}});
      await accept(result, version);
    } catch (error) {
      if (!current(version)) return;
      if (uuid(error.detail?.checkout_id)) checkoutId = error.detail.checkout_id;
      // A lost response or 5xx may follow a committed order: read first, never POST automatically.
      if (!error.status || error.status >= 500 || error.status === 409) await loadCart();
      else {phase = 'unknown'; feedback('checkout-error', error.message); await lookup(version);}
    } finally {if (current(version)) {working = false; render();}}
  }
  $('add-form').addEventListener('submit', event => {
    event.preventDefault(); if (!selectedProduct) return;
    const quantity = Number($('add-quantity').value);
    if (!Number.isInteger(quantity) || quantity < 1 || quantity > 100) return;
    mutate('/cart/items', 'POST', {product_id: selectedProduct.id, quantity}, 'Producto agregado al carrito.');
  });
  $('refresh-cart').addEventListener('click', () => loadCart());
  $('confirm-order').addEventListener('click', () => submitOrder());
  $('resume-order').addEventListener('click', () => submitOrder(true));
  $('check-order').addEventListener('click', async () => {
    if (working || loading) return;
    const version = epoch; working = true; stopPolling(); render();
    try {await lookup(version);} finally {if (current(version)) {working = false; render();}}
  });
  return {
    product(product) {
      selectedProduct = product; $('add-quantity').value = '1'; $('add-quantity').max = String(Math.min(100, product.stock));
      feedback('add-status'); feedback('add-error'); render();
    },
    session(id) {
      if (id !== userId) {
        epoch++; userId = id; readVersion++; loading = false; working = false; uncertainCart = false;
        cart = null; resetCheckout();
        for (const name of ['cart-error', 'cart-status', 'add-error', 'add-status']) feedback(name);
      }
      render();
    },
    route(name) {
      view = name; stopPolling();
      if (name === 'cart' || name === 'checkout') {polls = 0; if (!working) loadCart();}
      render();
    }
  };
};
