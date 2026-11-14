(() => {
  'use strict';
  const app=document.getElementById('patient-app');if(!app)return;
  const nav=app.querySelector('.patient-sidebar [data-section="notifications"]');if(!nav)return;
  const badge=document.createElement('span');badge.className='patient-notification-count';badge.hidden=true;badge.setAttribute('aria-hidden','true');nav.append(badge);
  const region=document.createElement('div');region.className='patient-alert-region';region.setAttribute('aria-live','polite');region.setAttribute('aria-relevant','additions');document.body.append(region);
  const key='gesecit-notifications-'+app.dataset.patientId;let cursor=null;
  try{const stored=sessionStorage.getItem(key);if(stored!==null&&/^\d+$/.test(stored))cursor=stored}catch{}
  let busy=false,stopped=false,timer,alertTimer;const queue=[];
  function nextAlert(){
    if(region.childElementCount||!queue.length)return;
    const item=queue.shift(),card=document.createElement('section');card.className='patient-alert';
    const head=document.createElement('div');head.className='patient-alert-head';const title=document.createElement('strong');title.textContent=item.title;
    const close=document.createElement('button');close.type='button';close.className='patient-alert-close';close.setAttribute('aria-label','Cerrar aviso');close.textContent='×';
    const body=document.createElement('p');body.textContent=item.body;
    const open=document.createElement('button');open.type='button';open.className='patient-alert-open';open.textContent='Ver notificaciones';
    function dismiss(){clearTimeout(alertTimer);card.remove();nextAlert()}
    close.addEventListener('click',dismiss);open.addEventListener('click',()=>{nav.click();dismiss()});head.append(title,close);card.append(head,body,open);region.append(card);
    const schedule=()=>{clearTimeout(alertTimer);alertTimer=setTimeout(dismiss,12000)};card.addEventListener('mouseenter',()=>clearTimeout(alertTimer));card.addEventListener('mouseleave',schedule);card.addEventListener('focusin',()=>clearTimeout(alertTimer));card.addEventListener('focusout',schedule);schedule();
  }
  async function check(){
    clearTimeout(timer);if(stopped||busy||document.hidden)return;
    busy=true;
    try{
      const url=new URL(app.dataset.notificationFeed,location.origin);if(cursor!==null)url.searchParams.set('after',cursor);
      const response=await fetch(url,{credentials:'same-origin',cache:'no-store'});
      if(response.redirected||response.status===401||response.status===403){stopped=true;return}
      if(!response.ok)throw new Error('Notification feed unavailable');
      const data=await response.json();cursor=data.cursor;try{sessionStorage.setItem(key,String(cursor))}catch{}
      badge.hidden=data.unread_count===0;badge.textContent=data.unread_count>99?'99+':String(data.unread_count);nav.setAttribute('aria-label',data.unread_count?'Notificaciones, '+data.unread_count+' sin leer':'Notificaciones');
      if(data.initial&&data.unread_count)queue.push({title:'Tienes notificaciones pendientes',body:'Hay '+data.unread_count+' notificaciones sin leer en tu cuenta.'});
      for(const item of data.items)queue.push(item);nextAlert();
      if(data.items.length&&nav.classList.contains('active')&&!document.querySelector('#patient-section form[data-saving="true"]'))nav.click();
    }catch{/* Reintentar sin interrumpir el trabajo del paciente. */}
    finally{busy=false;if(!stopped&&!document.hidden)timer=setTimeout(check,8000)}
  }
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(timer);else check()});window.addEventListener('focus',check);document.addEventListener('patient-content-updated',check);check();
})();
