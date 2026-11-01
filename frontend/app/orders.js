'use strict';
window.NexoOrders = function ({api, state, $, feedback, element, money}) {
  let owner = null, epoch = 0, view = 'catalog', selected = null, order = null;
  let page = 0, listRequest = 0, detailRequest = 0, loading = false, cancelling = false;
  let timer, polls = 0;
  const labels = {PENDING: 'Pendiente de pago', PAID: 'Pagado', CANCELLING: 'Cancelación en curso', CANCELLED: 'Cancelado', PROCESSING: 'En preparación', SHIPPED: 'Enviado', DELIVERED: 'Entregado'};
  const date = value => value ? new Date(value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z').toLocaleString('es-BO') : '';
  const signed = () => owner !== null && Boolean(state.token && state.user);
  const current = version => version === epoch && signed();
  const stop = () => {clearTimeout(timer); timer = undefined;};
  // Reuse the payment component with separate IDs/state for historical orders.
  const clone = $('payment-panel').cloneNode(true);
  for (const node of [clone, ...clone.querySelectorAll('[id]')]) node.id = 'history-' + node.id;
  clone.querySelectorAll('[for]').forEach(node => node.htmlFor = 'history-' + node.htmlFor);
  clone.setAttribute('aria-labelledby', 'history-payment-title'); $('history-payment-slot').append(clone);
  const payments = window.NexoPayments({api, state, money,
    $: id => $('history-' + id), feedback: (id, message) => feedback('history-' + id, message),
    onOrder(result) {if (order?.id === result.id) {order = result; renderDetail();}}
  });
  function render() {
    $('orders-login').hidden = signed(); $('orders-private').hidden = !signed();
    $('orders-filters').hidden = Boolean(selected); $('orders-list').hidden = Boolean(selected);
    $('orders-pagination').hidden = Boolean(selected); $('refresh-orders').hidden = Boolean(selected && order);
    $('refresh-orders').textContent = selected ? 'Volver a consultar pedido' : 'Actualizar historial';
    $('history-detail').hidden = !selected || !order || !signed();
    $('orders-list').setAttribute('aria-busy', String(loading)); $('refresh-orders').disabled = loading;
    renderDetail();
  }
  function renderDetail() {
    $('history-title').textContent = order ? `Pedido #${order.id}` : '';
    $('history-date').textContent = order ? date(order.created_at) : '';
    $('history-state').textContent = order ? labels[order.status] || order.status : '';
    $('history-total').textContent = order ? `Total: Bs ${money(order.total)}` : '';
    $('history-items').replaceChildren();
    for (const item of order?.items || []) {
      const row = element('div', undefined, 'review-row');
      row.append(element('span', `${item.product_name} × ${item.quantity}`), element('strong', `Bs ${money(item.subtotal)}`));
      $('history-items').append(row);
    }
    $('cancel-order').hidden = !order || order.status !== 'PENDING';
    $('cancel-order').disabled = cancelling || loading;
    $('refresh-order').disabled = cancelling || loading;
    payments.order(signed() ? order : null);
  }
  async function list() {
    if (!signed()) return;
    const version = epoch, request = ++listRequest;
    loading = true; $('orders-list').replaceChildren(); feedback('orders-error');
    $('orders-status').textContent = 'Consultando pedidos…'; $('orders-previous').disabled = true; $('orders-next').disabled = true; render();
    const query = new URLSearchParams({skip: String(page * 10), limit: '11'});
    if ($('order-filter').value) query.set('status', $('order-filter').value);
    try {
      const rows = await api(`/orders?${query}`, {authenticated: true});
      if (!current(version) || request !== listRequest || selected || view !== 'orders') return;
      $('orders-status').textContent = rows.length ? `${Math.min(rows.length, 10)} pedidos en esta página` : 'No hay pedidos con estos filtros.';
      for (const value of rows.slice(0, 10)) {
        const card = element('article', undefined, 'history-card');
        card.append(element('h2', `Pedido #${value.id}`), element('p', date(value.created_at)),
          element('p', labels[value.status] || value.status), element('strong', `Bs ${money(value.total)}`));
        const link = element('a', `Ver pedido #${value.id}`, 'button secondary'); link.href = `#pedidos/${value.id}`; card.append(link);
        $('orders-list').append(card);
      }
      $('orders-previous').disabled = page === 0; $('orders-next').disabled = rows.length <= 10; $('orders-page').textContent = `Página ${page + 1}`;
    } catch (error) {
      if (current(version) && request === listRequest) {feedback('orders-error', error.message); $('orders-status').textContent = 'No se pudo cargar el historial.';}
    } finally {if (current(version) && request === listRequest) {loading = false; render();}}
  }
  function schedule(version) {
    stop(); if (!current(version) || view !== 'orders' || !selected || polls >= 10) return;
    timer = setTimeout(() => {polls++; detail();}, 2500);
  }
  async function detail() {
    if (!signed() || !selected) return;
    const version = epoch, request = ++detailRequest, id = selected;
    loading = true; feedback('history-error'); feedback('orders-error'); render();
    $('orders-status').textContent = 'Consultando pedido…';
    try {
      const value = await api(`/orders/${id}`, {authenticated: true});
      if (!current(version) || request !== detailRequest || id !== selected || view !== 'orders') return;
      order = value; $('orders-status').textContent = ''; $('history-detail').hidden = false;
      if (order.status === 'CANCELLING') {feedback('history-status', 'Cancelación en curso. Consultaremos el resultado sin volver a enviarla.'); schedule(version);}
      else {
        feedback('history-status', order.status === 'CANCELLED' ? 'Pedido cancelado.' : '');
        if (order.status === 'PENDING') {polls = 0; schedule(version);}
        else stop();
      }
    } catch (error) {
      if (!current(version) || request !== detailRequest) return;
      stop(); order = null; $('orders-status').textContent = '';
      feedback('orders-error', error.status === 404 ? 'No encontramos este pedido en tu cuenta.' : error.message);
    } finally {if (current(version) && request === detailRequest) {loading = false; render();}}
  }
  $('cancel-order').addEventListener('click', () => {
    if (!order || order.status !== 'PENDING' || cancelling || loading) return;
    $('cancel-description').textContent = `Vas a cancelar el pedido #${order.id}. Esta acción no se puede deshacer.`;
    $('cancel-dialog').showModal(); $('keep-order').focus();
  });
  $('keep-order').addEventListener('click', () => $('cancel-dialog').close());
  $('cancel-dialog').addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const buttons = [...$('cancel-dialog').querySelectorAll('button:not(:disabled)')];
    const first = buttons[0], last = buttons[buttons.length - 1];
    if (event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
    else if (!event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
  });
  $('confirm-cancel').addEventListener('click', async () => {
    if (!order || order.status !== 'PENDING' || cancelling || loading) return;
    const version = epoch, id = order.id;
    $('cancel-dialog').close(); cancelling = true; stop(); render(); feedback('history-error');
    try {
      const value = await api(`/orders/${id}/cancel`, {method: 'POST', authenticated: true});
      if (!current(version) || selected !== id) return;
      order = value;
      feedback('history-status', value.status === 'CANCELLED' ? 'Pedido cancelado.' : 'La cancelación está en proceso.');
      if (value.status === 'CANCELLING') {polls = 0; schedule(version);}
    } catch (error) {
      if (!current(version) || selected !== id) return;
      const message = error.message;
      // Read the authoritative state after lost responses or a confirmed-payment conflict.
      await detail();
      if (current(version) && selected === id) feedback('history-error', message);
    } finally {if (current(version)) {
      cancelling = false; render();
      if (view === 'orders' && selected === id && order && document.activeElement === document.body) {
        const target = order.status === 'PENDING' ? $('cancel-order') : $('history-state');
        target.tabIndex = order.status === 'PENDING' ? 0 : -1;
        target.focus({preventScroll: true});
      }
    }}
  });
  $('orders-filters').addEventListener('submit', event => {event.preventDefault(); page = 0; list();});
  $('refresh-orders').addEventListener('click', () => selected ? detail() : list());
  $('orders-previous').addEventListener('click', () => {if (page > 0) {page--; list();}});
  $('orders-next').addEventListener('click', () => {page++; list();});
  $('refresh-order').addEventListener('click', () => {stop(); detail();});
  return {
    session(id) {
      payments.session(id);
      if (id !== owner) {
        epoch++; owner = id; listRequest++; detailRequest++; stop(); order = null; loading = false; cancelling = false; page = 0;
        $('orders-list').replaceChildren(); $('order-filter').value = '';
        for (const key of ['orders-error', 'orders-status', 'history-error', 'history-status']) feedback(key);
        $('cancel-dialog').close();
      }
      render();
    },
    route(name, id) {
      view = name; selected = id; stop(); polls = 0; listRequest++; detailRequest++; loading = false;
      $('cancel-dialog').close(); payments.route(name === 'orders' && id ? 'checkout' : 'catalog');
      if (name === 'orders') {order = null; if (id) detail(); else list();}
      else {order = null; feedback('orders-error');}
      render();
    }
  };
};
