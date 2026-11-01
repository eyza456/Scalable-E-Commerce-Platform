'use strict';
// Administrative user console. It intentionally exposes only the role and active flag
// already authorized by the user-service API; no passwords or sensitive fields are shown.
window.NexoAdmin = function ({api, state, $, element}) {
  let owner = null, epoch = 0, users = [], loading = false, query = '', statusMessage = '';
  const roles = ['Customer', 'seller', 'admin'];
  const current = version => version === epoch && state.token && state.user?.id === owner && state.user?.role === 'admin';
  const formatDate = value => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? String(value) : new Intl.DateTimeFormat('es-BO', {dateStyle: 'medium'}).format(date);
  };
  function render() {
    const admin = owner !== null && state.user?.role === 'admin' && Boolean(state.token);
    $('admin-private').hidden = !admin;
    $('admin-denied').hidden = admin;
    $('admin-users').setAttribute('aria-busy', String(loading));
    if (!admin) { $('admin-users').replaceChildren(); return; }
    const needle = query.trim().toLocaleLowerCase();
    const visible = users.filter(user => !needle || `${user.name} ${user.email} ${user.role}`.toLocaleLowerCase().includes(needle));
    $('admin-users').replaceChildren(...visible.map(userRow));
    $('admin-status').textContent = loading ? 'Cargando usuarios…' : statusMessage || `${visible.length} de ${users.length} usuarios mostrados.`;
  }
  function userRow(user) {
    const row = document.createElement('tr');
    const identity = document.createElement('td');
    identity.append(element('strong', user.name), element('span', user.email, 'admin-email'), element('small', `Alta: ${formatDate(user.create_at)}`));
    const roleCell = document.createElement('td');
    const roleLabel = element('label', `Rol de ${user.name}`, 'sr-only');
    const role = document.createElement('select'); role.id = `admin-role-${user.id}`; role.setAttribute('aria-label', `Rol de ${user.name}`);
    for (const value of roles) { const option = element('option', value === 'Customer' ? 'Cliente' : value === 'seller' ? 'Vendedor' : 'Administrador'); option.value = value; option.selected = user.role === value; role.append(option); }
    roleLabel.htmlFor = role.id; roleCell.append(roleLabel, role);
    const stateCell = document.createElement('td');
    const activeLabel = document.createElement('label'); activeLabel.className = 'admin-active';
    const active = document.createElement('input'); active.type = 'checkbox'; active.checked = Boolean(user.is_active); active.id = `admin-active-${user.id}`; active.setAttribute('aria-label', `${user.is_active ? 'Desactivar' : 'Activar'} ${user.name}`);
    activeLabel.append(active, element('span', user.is_active ? 'Activo' : 'Inactivo')); stateCell.append(activeLabel);
    const actionCell = document.createElement('td');
    const save = element('button', 'Guardar', 'secondary'); save.type = 'button'; save.id = `admin-save-${user.id}`;
    const isSelf = state.user?.id === user.id;
    if (isSelf) {
      role.disabled = true; active.disabled = true; save.disabled = true; save.title = 'No puedes cambiar tu propia cuenta desde aquí';
      actionCell.append(save, element('small', 'Tu cuenta')); row.classList.add('admin-self');
    } else {
      save.addEventListener('click', () => updateUser(user, role, active, save)); actionCell.append(save);
    }
    row.append(identity, roleCell, stateCell, actionCell); return row;
  }
  async function load() {
    if (!state.token || state.user?.role !== 'admin') { users = []; render(); return; }
    const version = epoch; loading = true; statusMessage = ''; $('admin-error').hidden = true; render();
    try {
      const result = await api('/users?skip=0&limit=100', {authenticated: true});
      if (!current(version)) return;
      users = Array.isArray(result) ? result : [];
      statusMessage = `${users.length} usuarios cargados.`;
    } catch (error) {
      if (!current(version)) return;
      $('admin-error').textContent = error.message; $('admin-error').hidden = false; users = [];
    } finally { if (current(version)) { loading = false; render(); } }
  }
  async function updateUser(user, role, active, save) {
    if (!current(epoch) || user.id === state.user.id || save.disabled) return;
    const changes = {};
    if (role.value !== user.role) changes.role = role.value;
    if (active.checked !== Boolean(user.is_active)) changes.is_active = active.checked;
    if (!Object.keys(changes).length) { statusMessage = 'No hay cambios para guardar.'; render(); return; }
    save.disabled = true; role.disabled = true; active.disabled = true; $('admin-error').hidden = true;
    try {
      const updated = await api(`/users/${user.id}`, {method: 'PATCH', authenticated: true, body: changes});
      if (!current(epoch)) return;
      const index = users.findIndex(item => item.id === user.id); if (index >= 0) users[index] = updated;
      statusMessage = `Cambios guardados para ${updated.name}.`; render();
    } catch (error) {
      if (!current(epoch)) return;
      role.value = user.role; active.checked = Boolean(user.is_active); $('admin-error').textContent = error.message; $('admin-error').hidden = false;
      save.disabled = false; role.disabled = false; active.disabled = false;
    }
  }
  $('admin-toolbar').addEventListener('submit', event => { event.preventDefault(); query = $('admin-search').value; statusMessage = ''; render(); });
  $('admin-refresh').addEventListener('click', () => load());
  return {
    session(id) {
      if (id !== owner) { epoch++; owner = id; users = []; query = ''; statusMessage = ''; $('admin-search').value = ''; $('admin-error').hidden = true; }
      render();
      if (state.user?.role === 'admin' && id !== null && !loading) load();
    },
    route(view) { if (view === 'admin' && state.user?.role === 'admin' && !users.length && !loading) load(); }
  };
};
