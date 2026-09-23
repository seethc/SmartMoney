'use strict';
const el=s=>document.querySelector(s);
const escapeHtml=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let statusData=null;
async function request(path,body,method='POST'){
  const res=await fetch('/api/openbanking/'+path+'?dataset=personal',{method,headers:{'Content-Type':'application/json','X-SmartMoney':'local'},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
  const data=await res.json();if(!res.ok)throw new Error(typeof data.detail==='string'?data.detail:'Check the application ID and try again.');return data;
}
async function task(button,fn){
  const text=button.textContent;button.disabled=true;button.textContent='Working…';el('#connection-error').textContent='';
  try{await fn();}catch(e){el('#connection-error').textContent=e.message;el('#connection-error').scrollIntoView({block:'center',behavior:'smooth'});}
  finally{button.disabled=false;button.textContent=text;if(button.id==='prepare'&&statusData?.prepared){button.disabled=true;button.textContent='Local key ready';}}
}
async function reloadStatus(){
  statusData=await request('status',undefined,'GET');
  el('#key-status').textContent=statusData.prepared?statusData.storage:'Not prepared';
  el('#certificate').hidden=!statusData.prepared;
  el('#callback-url').value=statusData.callback_url;
  el('#connection-origin').textContent=statusData.public_url;
  el('#prepare').textContent=statusData.prepared?'Local key ready':'Prepare connection';
  el('#prepare').disabled=statusData.prepared;
  el('#provider-status').textContent=statusData.configured?(statusData.active?'Production verified':'Production · activation needed'):'Not configured';
  if(statusData.app_id)el('[name=app_id]').value=statusData.app_id;
  el('#load-banks').disabled=!statusData.configured;
  const sessions=statusData.connections||[];
  el('#sync').disabled=!sessions.some(s=>s.active&&!s.expired);
  el('#connections').innerHTML=sessions.length?sessions.map(s=>`<div class="account-row"><div><strong>${escapeHtml(s.bank)}</strong><div class="account-meta">${s.accounts} authorised accounts · ${s.active?(s.expired?'Consent expired · reconnect using the bank selector above. Previous end date: ':'Consent ends ')+escapeHtml(s.valid_until?.slice(0,10)||'unknown'):'Disconnected'}</div><div class="account-meta">Last successful sync: ${s.last_sync?escapeHtml(new Date(s.last_sync).toLocaleString()):'Not synced'}</div></div>${s.active?`<button class="quiet" data-disconnect="${s.index}">Disconnect</button>`:''}</div>`).join(''):'<p class="helper">No banks connected yet.</p>';
}
el('#prepare').addEventListener('click',()=>task(el('#prepare'),async()=>{await request('prepare',{});await reloadStatus();}));
el('#provider-form').addEventListener('submit',event=>{event.preventDefault();task(el('#verify'),async()=>{await request('configure',{app_id:el('[name=app_id]').value.trim()});await reloadStatus();});});
el('#load-banks').addEventListener('click',()=>task(el('#load-banks'),async()=>{
  const data=await request('banks',{});
  el('#bank-list').innerHTML='<option value="">Choose your bank</option>'+data.banks.map(b=>`<option value="${escapeHtml(b.name)}">${escapeHtml(b.name)}${b.beta?' (beta)':''}</option>`).join('');
  el('#bank-list').disabled=false;el('#connect').disabled=!data.active;
  if(!data.active)el('#connection-error').textContent='Your application is not active yet. Link your own account in the Enable Banking control panel, then verify it again.';
  if(!data.banks.length)el('#connection-error').textContent='The provider returned no available UK personal banks for this application.';
}));
el('#bank-form').addEventListener('submit',event=>{event.preventDefault();task(el('#connect'),async()=>{
  if(!statusData||location.origin!==statusData.public_url)throw new Error('Open '+(statusData?.public_url||'the configured app address')+'/connections.html before starting consent.');
  const data=await request('connect',{bank:el('#bank-list').value});location.assign(data.url);
});});
el('#sync').addEventListener('click',()=>task(el('#sync'),async()=>{
  el('#sync-result').textContent='Reading bank balances and transaction pages. This can take a little while…';
  try{
    const result=await request('sync',{});
    const skipped=Object.entries(result.skipped).map(([key,count])=>`${count} ${key.replaceAll('_',' ')}`).join('; ');
    el('#sync-result').textContent=`Updated ${result.accounts_updated} accounts. Imported ${result.imported} new transactions; ${result.changed} changed. ${skipped?'Skipped: '+skipped+'. ':''}Review the imported transactions in your dashboard before using spending totals.`;
    await reloadStatus();
  }catch(e){el('#sync-result').textContent='Sync did not complete. See the error above.';throw e;}
}));
el('#connections').addEventListener('click',event=>{
  const button=event.target.closest('[data-disconnect]');if(!button)return;
  if(!window.confirm('Revoke this Enable Banking session? Your local account history will be retained.'))return;
  task(button,async()=>{await request('disconnect/'+button.dataset.disconnect,{});await reloadStatus();});
});
try{localStorage.setItem('smartmoney-workspace','personal');}catch{}
reloadStatus().catch(e=>el('#connection-error').textContent=e.message);
