(() => {
  'use strict';
  const app = document.getElementById('patient-app');
  if (!app) return;
  const chat = document.getElementById('patient-chat');
  const section = document.getElementById('patient-section');
  const log = document.getElementById('patient-messages');
  const composer = document.getElementById('patient-composer');
  const input = composer.elements.message;
  const token = composer.querySelector('[name=csrfmiddlewaretoken]').value;
  let busy = false;
  let navigation = 0;
  const scroll = () => { log.scrollTop = log.scrollHeight; };
  function message(text, user = false) {
    const row = document.createElement('div');
    row.className = 'patient-message' + (user ? ' user' : '');
    const avatar = document.createElement('span');
    avatar.className = 'patient-avatar';
    avatar.innerHTML = '<svg aria-hidden="true"><use href="#pi-' + (user ? 'user' : 'robot') + '"/></svg>';
    const bubble = document.createElement('div');
    bubble.className = 'patient-bubble';
    bubble.textContent = text;
    row.append(avatar, bubble); log.append(row); scroll();
  }
  async function show(name) {
    const current = ++navigation;
    app.querySelectorAll('.patient-sidebar [data-section]').forEach(button => {
      button.classList.toggle('active', button.dataset.section === name);
      if (button.dataset.section === name) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
    chat.hidden = name !== 'chat'; section.hidden = name === 'chat';
    if (name === 'chat') { input.focus(); return; }
    section.textContent = 'Cargando…';
    try {
      const response = await fetch(app.dataset.sectionUrl.replace('SECTION', name), {credentials: 'same-origin'});
      if (!response.ok || response.redirected) throw new Error('No se pudo cargar esta sección. Comprueba tu sesión e inténtalo de nuevo.');
      const html = await response.text();
      if (current === navigation) section.innerHTML = html;
    } catch (error) { if (current === navigation) section.textContent = error.message; }
  }
  async function send(text) {
    text = text.trim(); if (!text || busy) return;
    show('chat'); busy = true; composer.querySelector('button').disabled = true;
    log.querySelectorAll('.patient-choices').forEach(element => element.remove());
    message(text, true); input.value = '';
    try {
      const response = await fetch(app.dataset.chatUrl, {method:'POST', credentials:'same-origin', headers:{'X-CSRFToken':token}, body:new URLSearchParams({message:text})});
      if (response.redirected) throw new Error('Tu sesión ha terminado. Vuelve a iniciar sesión.');
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'No se pudo enviar el mensaje.');
      message(data.reply);
      if (data.options.length) {
        const choices = document.createElement('div'); choices.className = 'patient-choices';
        data.options.forEach(option => { const button = document.createElement('button'); button.type = 'button'; button.dataset.message = option; button.textContent = option; choices.append(button); });
        log.append(choices); scroll();
      }
    } catch (error) { message(error.message || 'No se pudo conectar. Inténtalo nuevamente.'); }
    finally { busy = false; composer.querySelector('button').disabled = false; if (!chat.hidden) input.focus(); }
  }
  app.addEventListener('click', event => {
    const nav = event.target.closest('[data-section]');
    if (nav) { show(nav.dataset.section); return; }
    const option = event.target.closest('[data-message]');
    if (option) send(option.dataset.message);
  });
  composer.addEventListener('submit', event => { event.preventDefault(); send(input.value); });
  section.addEventListener('submit', async event => {
    const form = event.target; if (!form.matches('[data-patient-form]')) return;
    event.preventDefault(); const button = form.querySelector('button[type=submit]'); if (button) button.disabled = true;
    try {
      const response = await fetch(form.action, {method:'POST', headers:{'X-CSRFToken':token}, body:new FormData(form)});
      if (!response.ok || response.redirected) throw new Error('No se pudieron guardar los cambios. Revisa tu sesión.');
      section.innerHTML = await response.text();
    } catch (error) { const notice = document.createElement('p'); notice.className = 'patient-error'; notice.textContent = error.message; form.prepend(notice); if(button) button.disabled = false; }
  });
  app.querySelectorAll('.patient-sidebar button').forEach(button => { button.setAttribute('aria-label',button.textContent.trim()); button.title = button.textContent.trim(); });
})();
