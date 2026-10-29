'use strict';
window.NexoProfile = function ({api, state, $, feedback, syncAccount}) {
  let owner = null, epoch = 0, editing = false, working = false;
  const current = (version, token) => epoch === version && state.token === token && state.user?.id === owner && owner !== null;
  function fill() {
    $('edit-name').value = state.user?.name || '';
    $('edit-email').value = state.user?.email || '';
  }
  function render() {
    $('profile-form').hidden = !editing || owner === null;
    $('edit-profile').hidden = editing || owner === null;
    for (const node of $('profile-form').elements) node.disabled = working;
    $('profile-form').setAttribute('aria-busy', String(working));
  }
  function signOutUnknown(email) {
    state.token = null; state.user = null; syncAccount();
    $('login-form').reset(); $('login-email').value = email;
    feedback('account-status', 'No se confirmó el resultado del cambio y cerramos esta sesión local. Inicia sesión de nuevo; si el cambio de correo se aplicó, usa el nuevo correo. No se repetirá la actualización automáticamente.');
    location.hash = '#cuenta';
  }
  $('edit-profile').addEventListener('click', () => {
    if (owner === null || working) return;
    editing = true; fill(); feedback('profile-error'); feedback('profile-status'); render(); $('edit-name').focus();
  });
  $('discard-profile').addEventListener('click', () => {
    if (working) return;
    editing = false; fill(); feedback('profile-error'); feedback('profile-status', 'Cambios descartados.'); render(); $('edit-profile').focus();
  });
  $('profile-form').addEventListener('submit', async event => {
    event.preventDefault(); if (working || owner === null || !state.token) return;
    feedback('profile-error'); feedback('profile-status');
    const name = $('edit-name').value.trim(), email = $('edit-email').value.trim();
    if (name.length < 3 || name.length > 100) {feedback('profile-error', 'El nombre debe tener entre 3 y 100 caracteres.'); return;}
    const changes = {};
    if (name !== state.user.name) changes.name = name;
    if (email !== state.user.email) changes.email = email;
    if (!Object.keys(changes).length) {feedback('profile-status', 'No hay cambios para guardar.'); return;}
    const version = epoch, token = state.token, id = owner;
    working = true; render();
    try {
      const result = await api('/users/me', {method: 'PUT', authenticated: true, body: changes});
      if (!current(version, token)) return;
      if (result.id !== id || typeof result.access_token !== 'string' || !result.access_token || result.token_type !== 'bearer') {
        signOutUnknown(email); return;
      }
      const {access_token, token_type, ...user} = result;
      state.token = access_token; state.user = user;
      editing = false; fill(); syncAccount();
      feedback('profile-status', 'Perfil actualizado. Tu sesión sigue activa.');
    } catch (error) {
      if (!current(version, token)) return;
      if (!error.status || error.status >= 500) signOutUnknown(email);
      else feedback('profile-error', error.message);
    } finally {
      if (version === epoch && owner === id) {working = false; render();}
    }
  });
  return {
    session(id) {
      if (id !== owner) {
        epoch++; owner = id; editing = false; working = false;
        feedback('profile-error'); feedback('profile-status'); fill();
      }
      render();
    }
  };
};
