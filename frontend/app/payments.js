'use strict';
window.NexoPayments = function ({api, $, feedback, money, state, onOrder}) {
  let owner = null, order = null, result = null, phase = 'loading', working = false;
  let epoch = 0, view = 'catalog', timer, polls = 0;
  let uncertain = false, baseline = null, simulation = null, resumable = false;
  const reasons = {
    INSUFFICIENT_FUNDS: 'Pago simulado rechazado: fondos insuficientes.',
    EXPIRED_CARD: 'Pago simulado rechazado: tarjeta vencida.',
    CARD_DECLINED: 'Pago simulado rechazado por el emisor.',
    INSUFFICIENT_STOCK: 'Pago rechazado: no hay stock suficiente. No se confirmó ningún cobro.'
  };
  const current = version => version === epoch && owner !== null && Boolean(state.token && state.user);
  const stop = () => {clearTimeout(timer); timer = undefined;};
  function render() {
    $('payment-panel').hidden = !order || owner === null;
    $('payment-form').hidden = !order || !['ready', 'rejected'].includes(phase) || order.status !== 'PENDING' || uncertain;
    $('pay-button').disabled = working;
    $('simulation-result').disabled = working;
    $('pay-button').textContent = phase === 'rejected' ? 'Simular otro intento' : 'Simular pago';
    $('refresh-payment').disabled = working;
    $('resume-payment').hidden = !resumable || !uncertain;
    $('resume-payment').disabled = working;
    $('payment-result').hidden = !result;
    $('payment-reference').textContent = result?.transaction_id || '';
    $('payment-amount').textContent = result ? `Bs ${money(result.amount)}` : '';
    const date = result?.processed_at ? new Date(result.processed_at) : null;
    $('payment-date').textContent = date && !Number.isNaN(date.getTime()) ? date.toLocaleString('es-BO') : result ? 'Pendiente' : '';
  }
  function clear() {
    epoch++; stop(); order = null; result = null; phase = 'loading'; working = false;
    uncertain = false; baseline = null; simulation = null; resumable = false; polls = 0;
    feedback('payment-status'); feedback('payment-error'); render();
  }
  function schedule(version) {
    stop();
    if (!current(version) || view !== 'checkout' || polls >= 10) return;
    timer = setTimeout(async () => {
      if (!current(version) || working) return;
      polls++; working = true; render();
      try {await read(version);} finally {if (current(version)) {working = false; render();}}
    }, 2500);
  }
  async function updateOrder(version) {
    const value = await api(`/orders/${order.id}`, {authenticated: true});
    if (!current(version)) return;
    order = value; onOrder(value);
  }
  async function accept(payment, version) {
    if (!current(version) || payment.order_id !== order.id) return;
    result = payment; resumable = false;
    if (uncertain && payment.id === baseline && payment.status === 'REJECTED') {
      phase = 'unknown'; resumable = true;
      feedback('payment-status', 'Solo se encontró el intento anterior. No se confirmó el resultado del último envío.');
      return;
    }
    uncertain = false; feedback('payment-error');
    if (payment.status === 'PAID') {
      phase = 'paid'; feedback('payment-status', 'Pago simulado aprobado. No se ha cobrado dinero real.');
      try {await updateOrder(version);} catch (error) {if (current(version)) feedback('payment-error', 'El pago está aprobado, pero no se pudo actualizar el estado del pedido. Consulta de nuevo.');}
      if (current(version) && order.status === 'PENDING') schedule(version);
    } else if (payment.status === 'REJECTED') {
      phase = 'rejected'; feedback('payment-status', reasons[payment.rejection_code] || 'Pago rechazado. Puedes simular otro intento.');
    } else if (payment.status === 'CANCELLED') {
      phase = 'cancelled'; feedback('payment-status', 'Este intento de pago fue cancelado.');
    } else {
      phase = 'pending'; feedback('payment-status', 'Pago en proceso. Consultaremos el resultado sin enviar otro pago.'); schedule(version);
    }
  }
  async function read(version = epoch, transaction = null) {
    if (!order || !current(version)) return;
    try {
      const path = transaction ? `/payments/transactions/${encodeURIComponent(transaction)}` : `/payments/orders/${order.id}/latest`;
      const payment = await api(path, {authenticated: true});
      // Transaction lookup has no numeric attempt ID: a known reference already identifies this submission.
      if (transaction && current(version)) uncertain = false;
      await accept(payment, version);
    } catch (error) {
      if (!current(version)) return;
      stop();
      if (error.status === 404 && !transaction) {
        if (uncertain) {
          phase = 'unknown'; resumable = true;
          feedback('payment-status', 'No se encontró un intento registrado. Puedes consultar de nuevo o reintentar la misma simulación de forma explícita.');
        } else {
          result = null; phase = 'ready'; feedback('payment-status', 'Aún no hay pagos registrados para este pedido.');
        }
        feedback('payment-error');
      } else {
        phase = 'unknown'; feedback('payment-error', error.message);
        feedback('payment-status', 'No se pudo confirmar el estado del pago. Consulta antes de volver a intentarlo.');
      }
    }
  }
  async function refresh() {
    if (!order || working || owner === null) return;
    const version = epoch; stop(); working = true; render();
    try {await read(version);} finally {if (current(version)) {working = false; render();}}
  }
  async function submit(resume = false) {
    if (!order || working || !current(epoch)) return;
    if (resume ? !uncertain || !resumable : !['ready', 'rejected'].includes(phase) || uncertain) return;
    const version = epoch, requested = resume ? simulation : $('simulation-result').value;
    stop(); working = true; resumable = false; render(); feedback('payment-error');
    try {
      // Recheck the latest attempt and order before every explicit submission.
      const previous = result?.id ?? null;
      await read(version);
      if (!current(version)) return;
      if (['paid', 'pending', 'cancelled'].includes(phase)) return;
      if (phase === 'unknown' && !resume) return;
      if (resume && result?.id !== previous && result !== null) return;
      if (phase === 'unknown' && !resumable) return;
      await updateOrder(version);
      if (!current(version)) return;
      if (order.status !== 'PENDING') {
        phase = 'blocked'; uncertain = false;
        feedback('payment-status', 'Este pedido ya no está pendiente de pago.'); return;
      }
      baseline = result?.id ?? null; simulation = requested;
      phase = 'submitting'; uncertain = true;
      feedback('payment-status', 'Procesando la simulación…'); render();
      try {
        const payment = await api('/payments', {method: 'POST', authenticated: true,
          body: {order_id: order.id, method: 'card', simulation_result: simulation}});
        if (current(version)) uncertain = false;
        await accept(payment, version);
      } catch (error) {
        if (!current(version)) return;
        if (typeof error.detail?.transaction_id === 'string') await read(version, error.detail.transaction_id);
        else {feedback('payment-error', error.message); await read(version);}
      }
    } catch (error) {
      if (current(version)) {phase = 'unknown'; feedback('payment-error', error.message);}
    } finally {if (current(version)) {working = false; render();}}
  }
  $('payment-form').addEventListener('submit', event => {event.preventDefault(); submit();});
  $('refresh-payment').addEventListener('click', refresh);
  $('resume-payment').addEventListener('click', () => submit(true));
  return {
    session(id) {if (id !== owner) {owner = id; clear();}},
    order(value) {
      if (value?.id !== order?.id) {
        clear(); order = value; render();
        if (order && owner !== null) refresh();
      } else {order = value; render();}
    },
    route(name) {view = name; stop(); if (name === 'checkout' && order && !working) refresh();}
  };
};
