const $ = (id) => document.getElementById(id);
const state = {spec: null, tasks: [], events: [], view:'board', editing:null, toasts:null};
const esc = (s='') => String(s).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api = async (url, method='GET', data) => {
  const response = await fetch(url, {method, headers: data === undefined ? {} : {'Content-Type':'application/json'}, body:data === undefined ? undefined : JSON.stringify(data)});
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {const body = await response.json(); detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);} catch(e){}
    throw new Error(detail);
  }
  return response.json();
};
function toast(text){const t=$('toast');t.textContent=text;t.classList.remove('hidden');clearTimeout(state.toasts);state.toasts=setTimeout(()=>t.classList.add('hidden'),2600)}
async function load(){
  [state.tasks,state.events] = await Promise.all([api('/api/tasks?include_closed=true'),api('/api/events')]);
  render();
}
function filtered(){
  const q=$('search').value.trim().toLowerCase(),p=$('priority-filter').value,closed=$('include-closed').checked;
  return state.tasks.filter(t => (closed || t.is_active) && (!p || t.priority===p) && (!q || t.title.toLowerCase().includes(q) || t.description.toLowerCase().includes(q) || t.tags.some(x=>x.toLowerCase().includes(q))));
}
function render(){
  const tasks=filtered(); $('task-count').textContent=`${tasks.length} task${tasks.length!==1?'s':''}`;
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.view===state.view));
  const content=$('content');
  if(state.view==='board'){
    content.className='board';
    content.innerHTML=state.spec.columns.map(col=>{
      const items=tasks.filter(t=>t.column===col.id);
      return `<section class="column" data-column="${esc(col.id)}" aria-label="${esc(col.label)} column"><header class="column-header"><div class="column-label">${esc(col.label)} <span class="column-count">${items.length}</span></div><button class="mini-plus" data-new-column="${esc(col.id)}" aria-label="New task in ${esc(col.label)}">+</button></header><div class="cards">${items.length?items.map(t=>card(t)).join(''):'<div class="empty">Drop a task here<br>or create a new one</div>'}</div></section>`;
    }).join('');
    content.querySelectorAll('[data-new-column]').forEach(b=>b.addEventListener('click',()=>openModal(null,b.dataset.newColumn)));
    content.querySelectorAll('[data-task]').forEach(el=>{
      el.addEventListener('click',()=>openModal(Number(el.dataset.task)));
      el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openModal(Number(el.dataset.task));}});
      el.addEventListener('dragstart',e=>{e.dataTransfer.setData('text/plain',el.dataset.task);el.classList.add('dragging')});
      el.addEventListener('dragend',()=>el.classList.remove('dragging'));
    });
    content.querySelectorAll('[data-column]').forEach(el=>{
      el.addEventListener('dragover',e=>{e.preventDefault();el.classList.add('drop-target')});
      el.addEventListener('dragleave',e=>{if(!el.contains(e.relatedTarget))el.classList.remove('drop-target')});
      el.addEventListener('drop',async e=>{e.preventDefault();el.classList.remove('drop-target');const id=Number(e.dataTransfer.getData('text/plain'));if(!id)return;try{await api(`/api/tasks/${id}`,'PATCH',{column:el.dataset.column});await load();toast('Task moved')}catch(err){toast(err.message)}});
    });
  } else if(state.view==='list'){
    content.className='list-panel';
    content.innerHTML='<div class="list-header"><span>ID</span><span>Task</span><span>Column</span><span>Priority</span><span>State</span></div>'+tasks.map(t=>`<div class="list-row" data-task="${t.id}" tabindex="0"><span>#${t.id}</span><span class="title">${esc(t.title)}</span><span>${esc(t.column)}</span><span>${esc(t.priority)}</span><span>${t.is_active?'Open':'Closed'}</span></div>`).join('');
    content.querySelectorAll('[data-task]').forEach(el=>{el.onclick=()=>openModal(Number(el.dataset.task));el.onkeydown=e=>{if(e.key==='Enter')openModal(Number(el.dataset.task))}});
  } else {
    content.className='activity-panel';
    content.innerHTML=state.events.length?state.events.map(ev=>`<div class="activity-row"><span class="card-id">#${ev.task_id}</span><strong>${esc(ev.action.replaceAll('_',' '))}</strong><span>${esc(ev.details.title || ev.details.column || '')}</span><span class="date">${esc(new Date(ev.timestamp).toLocaleString())}</span></div>`).join(''):'<div class="activity-row">No activity yet</div>';
  }
}
function card(t){
  const tags=t.tags.slice(0,3).map(tag=>`<span class="tag">${esc(tag)}</span>`).join('');
  return `<article class="task-card ${t.is_active?'':'closed'}" draggable="true" tabindex="0" role="button" aria-label="Open task ${esc(t.title)}" data-task="${t.id}"><div class="card-top"><span class="card-id">#${t.id} ${t.is_active?'':'· Closed'}</span><span class="card-overflow">•••</span></div><div class="card-title">${esc(t.title)}</div><div class="card-bottom"><div class="tags">${tags}</div><span class="priority ${esc(t.priority)}">${esc(t.priority)}</span></div></article>`;
}
function openModal(id=null,column=null){
  const task = state.tasks.find(t=>t.id===id);
  state.editing=task?.id??null;
  $('modal-title').textContent=task?`Task #${task.id}`:'New task';
  $('field-title').value=task?.title??'';
  $('field-description').value=task?.description??'';
  $('field-column').value=task?.column??column??state.spec.default_column;
  $('field-priority').value=task?.priority??state.spec.default_priority;
  $('field-tags').value=task?.tags.join(', ')??'';
  $('form-error').classList.add('hidden');
  $('save-task').textContent=task?'Save changes':'Create task';
  $('task-close').classList.toggle('hidden',!task||!task.is_active);
  $('task-reopen').classList.toggle('hidden',!task||task.is_active);
  $('modal-backdrop').classList.remove('hidden');$('field-title').focus();
}
function closeModal(){$('modal-backdrop').classList.add('hidden');state.editing=null}
async function saveTask(event){
  event.preventDefault();
  const payload={title:$('field-title').value.trim(),description:$('field-description').value,priority:$('field-priority').value,column:$('field-column').value,tags:$('field-tags').value.split(',').map(x=>x.trim()).filter(Boolean)};
  if(!payload.title){$('form-error').textContent='Title is required';$('form-error').classList.remove('hidden');return}
  try {const wasEditing=Boolean(state.editing);if(wasEditing)await api(`/api/tasks/${state.editing}`,'PATCH',payload);else await api('/api/tasks','POST',payload);closeModal();await load();toast(wasEditing?'Task saved':'Task created')}
  catch(error){$('form-error').textContent=error.message;$('form-error').classList.remove('hidden')}
}
async function toggleActive(active){
  if(!state.editing)return;
  try{await api(`/api/tasks/${state.editing}/${active?'reopen':'close'}`,'POST');closeModal();await load();toast(active?'Task reopened':'Task closed')}
  catch(error){$('form-error').textContent=error.message;$('form-error').classList.remove('hidden')}
}
async function initialize(){
  state.spec=await api('/api/spec');
  $('project-name').textContent=state.spec.title;$('crumb-project').textContent=state.spec.title;$('subtitle').textContent=state.spec.subtitle;
  document.title=`${state.spec.title} · Board`;
  $('field-column').innerHTML=state.spec.columns.map(x=>`<option value="${esc(x.id)}">${esc(x.label)}</option>`).join('');
  $('field-priority').innerHTML=state.spec.priorities.map(x=>`<option>${esc(x)}</option>`).join('');
  $('priority-filter').innerHTML+=[...state.spec.priorities].map(x=>`<option>${esc(x)}</option>`).join('');
  $('new-task').onclick=()=>openModal();
  $('task-form').onsubmit=saveTask;
  $('task-close').onclick=()=>toggleActive(false);$('task-reopen').onclick=()=>toggleActive(true);
  $('close-modal').onclick=closeModal;$('cancel-modal').onclick=closeModal;
  $('modal-backdrop').addEventListener('click',e=>{if(e.target===$('modal-backdrop'))closeModal()});
  window.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal()});
  $('search').oninput=render;$('priority-filter').onchange=render;$('include-closed').onchange=render;
  document.querySelectorAll('.tab').forEach(t=>t.addEventListener('click',()=>{state.view=t.dataset.view;render()}));
  await load();
}
initialize().catch(e=>{document.querySelector('main').innerHTML=`<h1>Unable to load the environment</h1><p>${esc(e.message)}</p>`});
