'use strict';
const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let mode='balances', expectedRevision=0, revisionRequest=0, revisionReady=false;
let accounts=[], ready=false, busy=false, rowIndex=0, sourceIndex=0;
const money = n => new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP'}).format(n/100);
const localToday = () => {const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;};
async function api(path,options={}){
  const response=await fetch('/api/'+path+(path.includes('?')?'&':'?')+'dataset='+$('#workspace').value,{
    ...options,headers:{'X-SmartMoney':'local',...(options.headers||{})},cache:'no-store'});
  const result=await response.json();
  if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Check the account details, amounts and dates.');
  return result;
}
function clearDraft(){ mode='balances';expectedRevision=0;revisionRequest++;revisionReady=false;$('#spending-fields').hidden=true;$('#category-rows').replaceChildren();$('#balance-help').hidden=false;$('#spending-fields').querySelectorAll('input').forEach(i=>{i.value='';i.checked=false;i.required=false;});$('#replace-label').hidden=true;$('#existing-report').textContent=''; $('#rows').replaceChildren();$('#sources').replaceChildren();$('#review').hidden=true;$('#confirmed').checked=false;$('#save-error').textContent='';rowIndex=0;sourceIndex=0; }
function setBusy(value){busy=value;$('#workspace').disabled=value||sourceIndex>0||Boolean($('#rows').children.length);$('#read').disabled=value||!ready;$('#manual').disabled=value||mode==='spending';$('#spending-fields').disabled=value;$('#read').disabled=value||!ready||mode==='spending';$('#images').disabled=value;$('#save').disabled=value;$('#discard').disabled=value;$('#confirmed').disabled=value;for(const row of $('#rows').children)row.disabled=value;}
async function load(){
  try{
    setBusy(true);
    const [state, dashboard]=await Promise.all([api('screenshots/status'),api('dashboard')]);
    accounts=dashboard.accounts;ready=state.ocr_available;
    $('#status').textContent=ready?'Ready.':'Local OCR needs Tesseract. On the Pi: sudo apt install tesseract-ocr tesseract-ocr-eng. You can still enter balances manually.';
  }catch(e){$('#status').textContent=e.message;ready=false;}finally{setBusy(false);}
}
function addRow(candidate={},source='Manual entry'){
  const id=++rowIndex;
  const wrapper=document.createElement('fieldset');wrapper.className='snapshot-row skipped';wrapper.dataset.row=String(id);
  wrapper.innerHTML=`<legend>Balance ${id} · ${esc(source)}</legend>
    <p class="context helper">${esc(candidate.context||'Enter a balance you have checked yourself.')}${candidate.confidence!==undefined?`<br>OCR confidence: ${esc(candidate.confidence)}%`:''}</p>
    <div class="form-grid">
      <label class="field">Account<select name="target"><option value="skip">Skip this row</option><option value="new">Create a new account</option>${accounts.map(a=>`<option value="${a.id}">${esc(a.institution)} · ${esc(a.name)} (${esc(a.kind)})</option>`).join('')}</select></label>
      <label class="field">GBP balance<input name="balance" type="number" step="0.01" value="${esc(candidate.balance||'')}" required disabled></label>
      <label class="field">Balance last updated on<input name="balance_as_of" type="date" max="${localToday()}" required disabled></label>
      <div class="new-fields" hidden><label class="field">New account name<input name="name" value="${esc(candidate.label||'')}" maxlength="80" required disabled></label><label class="field">Bank / institution<input name="institution" maxlength="80" required disabled></label><label class="field">Account type<select name="kind" disabled><option value="current">Current</option><option value="savings">Savings</option><option value="credit">Credit card</option><option value="investment">Investment</option></select></label></div>
    </div><p class="previous helper"></p><button type="button" class="remove-row">Remove row</button>`;
  $('#rows').append(wrapper);$('#review').hidden=false;$('#success').hidden=true;$('#workspace').disabled=true;
  $('#confirmed').checked=false;
}
function applyTarget(row){
  const target=row.querySelector('[name=target]').value, skipped=target==='skip', fresh=target==='new';
  row.classList.toggle('skipped',skipped);row.querySelector('.new-fields').hidden=!fresh;
  row.querySelectorAll('input,select').forEach(input=>{if(input.name!=='target')input.disabled=skipped||(!fresh&&['name','institution','kind'].includes(input.name));});
  const previous=accounts.find(a=>String(a.id)===target);
  row.querySelector('.previous').textContent=previous?`Currently saved: ${money(previous.balance_pence)} as of ${previous.balance_as_of}. `:fresh?'Set buffers and allowances on the Accounts page.':'';
}
$('#rows').addEventListener('change',e=>{if(e.target.name==='target')applyTarget(e.target.closest('fieldset'));$('#confirmed').checked=false;});
$('#rows').addEventListener('input',()=>{$('#confirmed').checked=false;});
$('#rows').addEventListener('click',e=>{if(e.target.closest('.remove-row')){e.target.closest('fieldset').remove();$('#confirmed').checked=false;}});
$('#manual').addEventListener('click',()=>addRow());
$('#discard').addEventListener('click',()=>{clearDraft();$('#images').value='';setBusy(false);$('#status').textContent='Draft discarded.';});
$('#workspace').addEventListener('change',()=>{clearDraft();load();});
async function dataUrl(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(new Error('Could not read this file.'));reader.readAsDataURL(file);});}
$('#read').addEventListener('click',async()=>{
  const files=Array.from($('#images').files);
  if(!files.length||files.length>6){$('#status').textContent='Choose between one and six screenshots.';return;}
  if(sourceIndex+files.length>6){$('#status').textContent='This draft already has screenshots. Save or discard it before adding more than six.';return;}
  if(files.some(f=>f.size>8_000_000||!['image/png','image/jpeg','image/webp'].includes(f.type))){$('#status').textContent='Each file must be a PNG, JPEG or WebP image smaller than 8 MB.';return;}
  setBusy(true);let failures=0;
  try{
    for(const file of files){
      $('#status').textContent=`Reading ${file.name}…`;
      try{
        const result=await api('screenshots/preview',{method:'POST',headers:{'Content-Type':file.type},body:file});
        if(result.type==='spending'&&(files.length!==1||sourceIndex||rowIndex))throw new Error('Import one spending report at a time. Discard this draft first.');
        if(result.type==='spending')showSpending(result);
        sourceIndex++;
        const section=document.createElement('details');section.open=true;
        section.innerHTML=`<summary>Screenshot ${sourceIndex}: ${esc(file.name)}</summary><img class="source-preview" alt="Original screenshot"><ul>${result.notices.map(n=>`<li>${esc(n)}</li>`).join('')}</ul><details><summary>Extracted text</summary><pre>${esc(result.text)}</pre></details>`;
        section.querySelector('img').src=await dataUrl(file);$('#sources').append(section);$('#review').hidden=false;
        for(const candidate of result.candidates)addRow(candidate,`screenshot ${sourceIndex}`);
        $('#workspace').disabled=true;
      }catch(e){failures++;const error=document.createElement('p');error.textContent=`${file.name}: ${e.message}`;$('#sources').append(error);$('#review').hidden=false;}
    }
    $('#status').textContent=failures?`${failures} screenshot(s) could not be read. See details below; retry or add rows manually.`:'Review the extracted values below.';
    $('#images').value='';
  }finally{setBusy(false);}
});
$('#review-form').addEventListener('submit',async e=>{
  e.preventDefault();if(busy)return;$('#save-error').textContent='';
  if(mode==='spending'){await saveSpending();return;}
  const rows=[];
  for(const row of $('#rows').children){
    const value=name=>row.querySelector(`[name="${name}"]`).value;
    if(value('target')==='skip')continue;
    const item={balance:value('balance'),balance_as_of:value('balance_as_of')};
    if(value('target')==='new')Object.assign(item,{name:value('name'),institution:value('institution'),kind:value('kind')});
    else{const account=accounts.find(a=>String(a.id)===value('target'));Object.assign(item,{account_id:account.id,expected_balance_pence:account.balance_pence,expected_balance_as_of:account.balance_as_of});}
    rows.push(item);
  }
  if(!rows.length){$('#save-error').textContent='Select at least one account, or create a new account for a row.';return;}
  if(!$('#confirmed').checked)return;
  setBusy(true);
  try{
    const workspace=$('#workspace').value;
    const result=await api('screenshots/commit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed:true,rows})});
    clearDraft();$('#images').value='';
    try{localStorage.setItem('smartmoney-workspace',workspace);}catch{}
    $('#success').hidden=false;$('#success').innerHTML=`<h2>Balances saved</h2><p>${result.updated} updated · ${result.created} created · ${result.unchanged} already current.</p><a href="/#accounts">View accounts →</a>`;
    await load();
  }catch(error){$('#save-error').textContent=error.message;}finally{setBusy(false);}
});
load();

function showSpending(result){
  mode='spending';$('#balance-help').hidden=true;$('#spending-fields').hidden=false;
  $('#period-hint').textContent=result.month_hint?`${result.month_hint} detected. Enter the year and actual date range.`:'Enter the actual date range, including the year.';
  for(const id of ['report-start','report-end','report-scope','report-total'])$('#'+id).required=true;
  $('#report-start').max=localToday();$('#report-end').max=localToday();$('#report-total').value=result.total;
  result.rows.forEach(addCategory);reconcile();
}
function addCategory(row={label:'',amount:'',kind:'expense',count:null}){
  const element=document.createElement('div');element.className='category-edit';
  element.innerHTML=`<label class="field">Category<input name="label" value="${esc(row.label)}" maxlength="60" required></label><label class="field">Type<select name="kind">${[['expense','Spending'],['income','Income'],['transfer','Transfer'],['excluded','Excluded']].map(([key,label])=>`<option value="${key}" ${row.kind===key?'selected':''}>${label}</option>`).join('')}</select></label><label class="field">Amount (£)<input name="amount" type="number" step="0.01" value="${esc(row.amount)}" required></label><label class="field">Transactions<input name="count" type="number" min="0" max="1000000" step="1" value="${row.count??''}"></label><button type="button" class="remove-category" aria-label="Remove category">×</button>`;
  $('#category-rows').append(element);$('#confirmed').checked=false;
}
function categoryValues(){return Array.from($('#category-rows').children).map(row=>{const value=name=>row.querySelector(`[name="${name}"]`).value;return {label:value('label'),amount:value('amount'),kind:value('kind'),count:value('count')===''?null:Number(value('count'))};});}
function reconcile(){const rows=categoryValues().filter(r=>r.kind==='expense');const total=rows.reduce((sum,r)=>sum+Math.round(Number(r.amount)*100),0);const difference=total-Math.round(Number($('#report-total').value)*100);$('#reconciliation').textContent=`Categories: ${money(total)} · ${difference===0?'Total matches':'Difference: '+money(difference)}`;}
async function loadRevision(){
  const request=++revisionRequest;revisionReady=false;expectedRevision=0;$('#replace-report').checked=false;$('#replace-label').hidden=true;$('#existing-report').textContent='';
  const month=$('#report-start').value.slice(0,7);if(!month)return;
  try{const result=await api('spending-summaries/'+month);if(request!==revisionRequest)return;expectedRevision=result.summary?.revision||0;revisionReady=true;if(result.summary){$('#replace-label').hidden=false;$('#existing-report').textContent=`Saved: ${result.summary.start_date} to ${result.summary.end_date} · ${result.summary.scope} · ${money(result.summary.total_pence)}`;}}
  catch(e){if(request===revisionRequest)$('#existing-report').textContent=e.message;}
}
$('#report-start').addEventListener('change',loadRevision);
$('#add-category').addEventListener('click',()=>{addCategory();reconcile();});
$('#category-rows').addEventListener('click',e=>{if(e.target.closest('.remove-category')){e.target.closest('.category-edit').remove();$('#confirmed').checked=false;reconcile();}});
$('#spending-fields').addEventListener('input',()=>{$('#confirmed').checked=false;reconcile();});
async function saveSpending(){
  if(!revisionReady){$('#save-error').textContent='Reselect the start date to check for an existing report.';return;}
  if(!$('#confirmed').checked)return;
  const body={confirmed:true,start_date:$('#report-start').value,end_date:$('#report-end').value,scope:$('#report-scope').value,total:$('#report-total').value,rows:categoryValues(),expected_revision:expectedRevision,replace_existing:$('#replace-report').checked};
  setBusy(true);
  try{const result=await api('spending-summaries',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});try{localStorage.setItem('smartmoney-workspace',$('#workspace').value);localStorage.setItem('smartmoney-report-month',result.month);}catch{}clearDraft();$('#success').hidden=false;$('#success').innerHTML='<h2>Spending saved</h2><a href="/#spending">View spending →</a>';$('#status').textContent='Saved.';}
  catch(e){$('#save-error').textContent=e.message;}finally{setBusy(false);}
}
