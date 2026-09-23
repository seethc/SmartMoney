'use strict';
const $ = (s, root=document) => root.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = n => new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',minimumFractionDigits:2}).format(n/100);
const shortMoney = n => new Intl.NumberFormat('en-GB',{style:'currency',currency:'GBP',maximumFractionDigits:0}).format(n/100);
const dateLabel = value => new Date(value+'T12:00:00').toLocaleDateString('en-GB',{day:'numeric',month:'short'});
const monthLabel = value => new Date(value+'-01T12:00:00').toLocaleDateString('en-GB',{month:'long',year:'numeric'});
const colours = ['#5c846c','#94b49b','#b9c7a7','#d7bc8c','#b8cacc','#829cac','#d6dad4','#bbb2c9'];
const titles = {overview:'Overview',accounts:'Accounts',spending:'Spending',cashflow:'Cash flow',plan:'Transfer plan',transactions:'Transactions',data:'Data & settings'};
let data, view = titles[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
let dataset = 'demo', month = '', days = 30, search = '', filter = '', kindFilter = '', requestId = 0;
try { if(localStorage.getItem('smartmoney-workspace')==='personal') dataset='personal'; } catch {}
$('#dataset').value=dataset;
function rememberWorkspace(){try { localStorage.setItem('smartmoney-workspace',dataset); } catch {}}
let installPrompt = null;

async function api(path, options={}) {
  const response = await fetch('/api/'+path+(path.includes('?')?'&':'?')+'dataset='+dataset, {
    ...options, headers:{'Content-Type':'application/json','X-SmartMoney':'local',...(options.headers||{})}, cache:'no-store'
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Please check the fields and try again.');
  return result;
}
function toast(message) { $('#toast').textContent=message; $('#toast').style.display='block'; setTimeout(()=>$('#toast').style.display='none',4500); }
async function refresh() {
  const id = ++requestId;
  try {
    const result = await api('dashboard?days='+days+(month?'&month='+month:''));
    if (id !== requestId) return;
    data=result; month=data.month; render();
  } catch(e) {
    if (id !== requestId) return;
    $('#main').innerHTML=`<div class="empty"><h2>We couldn't load your workspace</h2><p>${esc(e.message)} Check that the local Python server is running.</p><button data-action="refresh">Try again</button></div>`;
  }
}
function nav(next) { view=next; location.hash=next; render(); window.scrollTo({top:0,behavior:'smooth'}); }
function accountName(id) { return data.accounts.find(a=>a.id===id)?.name || 'Account'; }
function bankIcon(a) { const css = /santander|revolut|chase|ulster/i.exec(a.institution)?.[0].toLowerCase() || '';return `<span class="bank-icon ${css}">${esc(a.institution[0])}</span>`; }
function periodSelect(){return `<select id="month" aria-label="Transaction month">${data.months.map(m=>`<option value="${m}" ${m===month?'selected':''}>${monthLabel(m)}</option>`).join('')}</select>`;}
function pageHeading(title, sub, actions=''){return `<div class="page-heading"><div><div class="eyebrow">YOUR MONEY, IN VIEW</div><h1>${title}</h1><p class="subtitle">${sub}</p></div><div class="heading-actions">${actions}</div></div>`;}
function demoBanner(){return dataset==='demo'?`<div class="demo-banner"><span>◈</span><span><b>A little preview of what's possible.</b> These are example balances and transactions, not your bank data.</span><button data-action="personal">Use my own data →</button></div>`:'';}
function empty(message, action=''){return `<div class="empty"><h2>A clearer picture starts here</h2><p>${message}</p>${action}</div>`;}
function metric(label,value,note,highlight=false,symbol='↗'){return `<div class="metric ${highlight?'highlight':''}"><div class="metric-label">${label}<span>${symbol}</span></div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></div>`;}
function render(){
  if(!data) return;
  $('#breadcrumb').textContent=titles[view];
  document.querySelectorAll('[data-view]').forEach(b=>{b.classList.toggle('active',b.dataset.view===view);b.setAttribute('aria-current',b.dataset.view===view?'page':'false');});
  $('#plan-count').textContent=data.forecast.recommendations.length;
  const pages={overview,accounts,spending,cashflow,plan,transactions,data:dataPage};
  $('#main').innerHTML=(data.unreviewed_count?`<div class="demo-banner"><span>!</span><span><b>${data.unreviewed_count} imported transactions need review.</b> Spending and income totals exclude these until you confirm their categories and types.</span><button data-action="review-imports">Review imports →</button></div>`:'')+pages[view]();
}
function alertBanner(){
  const r=data.forecast.recommendations[0];
  if(!r) return '';
  return `<section class="funding-banner"><div class="alert-icon">!</div><div><h3>A little heads-up: ${esc(r.name)} needs funding</h3><p>Projected low of ${money(r.minimum_pence)}. ${r.stale?'Refresh your balance before planning a transfer.':`Set aside ${money(r.needed_pence)} to keep your ${money(r.buffer_pence)} buffer.`}</p></div><button data-view="plan">Review transfer plan ↗</button></section>`;
}
function overview(){
  const f=data.forecast;
  return pageHeading('A clearer view of your money.',`All your accounts. One place. A little peace of mind.`,`${periodSelect()}<button class="primary" data-action="import">＋ Import data</button>`)+demoBanner()+
  `<div class="metrics">${metric('Net worth',money(data.net_worth_pence),'Across '+data.accounts.length+' recorded accounts',false,'◈')}${metric('Cash-flow headroom',f.stale?'Refresh needed':money(f.headroom_pence),`Estimate · after buffers & ${days}-day plan`,true,'↗')}${metric('Income this month',money(data.income_pence),'Reviewed income · transfers excluded',false,'↓')}${metric('Spent this month',money(data.spending_pence),'Reviewed spending · net of refunds',false,'↑')}</div>`+
  (data.accounts.length?alertBanner()+`<div class="grid-two">${accountsPanel()}${spendingPanel()}</div><div class="grid-two">${historyPanel()}${upcomingPanel()}</div>`:empty('Connect your bank to sync real balances and history, or add accounts manually. Your demo workspace remains separate.','<button class="primary" data-action="bank-setup">Connect my bank</button> <button data-action="add-account">Add account manually</button>'));
}
function accountsPanel(){return `<section class="panel"><div class="panel-heading"><div><h2>Your accounts</h2><p class="subtitle">The whole picture, at a glance</p></div><button class="text-link" data-view="accounts">View all ↗</button></div>${data.accounts.map(a=>{const low=data.forecast.minima[a.id]<a.buffer_pence && a.kind==='current';return `<div class="account-row">${bankIcon(a)}<div><div class="account-name">${esc(a.name)}</div><div class="account-meta">${esc(a.role || a.kind)}</div></div><div class="account-amount"><strong>${money(a.balance_pence)}</strong><small class="${low?'warning':''}">${a.balance_as_of!==data.today?'Snapshot '+dateLabel(a.balance_as_of):low?'◦ Funding needed':'Recorded '+dateLabel(a.balance_as_of)}</small></div></div>`;}).join('')}<div class="account-total"><span>Cash across current & savings accounts</span><strong>${money(data.cash_pence)}</strong></div></section>`;}
function spendingPanel(full=false){
  const entries=Object.entries(data.categories), positive=entries.filter(([,v])=>v>0), sum=positive.reduce((s,[,v])=>s+v,0);
  let start=0; const gradient=positive.map(([,v],i)=>{const end=start+v/sum*100;const part=`${colours[i%colours.length]} ${start}% ${end}%`;start=end;return part;}).join(',');
  return `<section class="panel"><div class="panel-heading"><div><h2>Where your money goes</h2><p class="subtitle">${monthLabel(month)} · actual spending</p></div>${full?'':`<button class="text-link" data-view="spending">Breakdown ↗</button>`}</div>${entries.length?`<div class="spending-layout"><div class="donut" role="img" aria-label="Spending by category. Values listed alongside." style="background:${sum?'conic-gradient('+gradient+')':'#eef2ec'}"><div class="donut-center"><small>Total spent</small><strong>${money(data.spending_pence)}</strong></div></div><div class="legend">${entries.map(([k,v],i)=>`<div class="legend-row"><i style="background:${colours[positive.findIndex(([p])=>p===k)%colours.length]||'#ccc'}"></i><span>${esc(k)}</span><strong>${money(v)}</strong></div>`).join('')}</div></div><div class="panel-footnote">Transfers between your accounts aren't spending. Refunds reduce their assigned category; net refund categories are excluded from the ring.</div>`:empty('Import transactions to see a breakdown of spending.')}</section>`;
}
function historyPanel(){
  const maximum=Math.max(1,...data.history.flatMap(h=>[h.income,h.spending]));
  return `<section class="panel"><div class="panel-heading"><div><h2>Money in, money out</h2><p class="subtitle">Your monthly cash flow</p></div><button class="text-link" data-view="cashflow">Explore ↗</button></div><div class="cash-summary"><div><label>Money in</label><strong>${money(data.income_pence)}</strong></div><div><label>Money out</label><strong>${money(data.spending_pence)}</strong></div><div><label>Net cash flow</label><strong class="${data.net_cashflow_pence>=0?'positive':'negative'}">${money(data.net_cashflow_pence)}</strong></div></div><div class="bar-chart" role="img" aria-label="Monthly recorded income and expenditure">${data.history.map(h=>`<div class="bar-group"><div class="bar" style="height:${Math.max(0,h.income)/maximum*90}%" title="Income ${money(h.income)}"></div><div class="bar spent" style="height:${Math.max(0,h.spending)/maximum*90}%" title="Spending ${money(h.spending)}"></div><span>${monthLabel(h.month).split(' ')[0].slice(0,3)}</span></div>`).join('')}</div><div class="key"><span><i style="background:#a9c5b6"></i>Income</span><span><i style="background:#e0e7e1"></i>Spending</span><span>Recorded transactions only</span></div></section>`;
}
function upcomingPanel(full=false){return `<section class="panel"><div class="panel-heading"><div><h2>Coming up next</h2><p class="subtitle">Planned payments · next ${days} days</p></div><button class="text-link" data-action="add-schedule">＋ Add</button></div>${data.forecast.events.slice(0,full?100:5).map(e=>`<div class="event-row"><div class="date-tile"><small>${new Date(e.date+'T12:00:00').toLocaleDateString('en-GB',{month:'short'})}</small><b>${Number(e.date.slice(-2))}</b></div><div><strong>${esc(e.name)}</strong><div class="account-meta">${esc(accountName(e.account_id))} · ${e.frequency==='monthly'?'Monthly':'One-off'}${e.target_account_id?' → '+esc(accountName(e.target_account_id)):''}</div></div><div class="amount ${e.amount_pence>0?'positive':''}">${money(e.amount_pence)}</div>${full?`<button class="quiet" data-action="remove-schedule" data-id="${e.id}" aria-label="Remove ${esc(e.name)} from forecast">×</button>`:''}</div>`).join('')||empty('Add your expected bills and income to build a forward view.')}<div class="panel-footnote">Estimates only. Make all payments in your banking apps.</div></section>`;}
function accounts(){return pageHeading('Every account, together.','Current accounts, savings, investments and credit — with their own purpose.','<button class="primary" data-action="add-account">＋ Add account</button>')+demoBanner()+`<div class="account-cards">${data.accounts.map(a=>`<section class="panel">${bankIcon(a)}<h2>${esc(a.name)}</h2><p class="subtitle">${esc(a.role || a.kind)}</p><div class="balance">${money(a.balance_pence)}</div><div class="detail-line"><span>Account type</span><span>${esc(a.kind)}</span></div><div class="detail-line"><span>Balance recorded</span><span>${dateLabel(a.balance_as_of)} ${a.balance_as_of!==data.today?'· stale':''}</span></div><div class="detail-line"><span>Safety buffer</span><span>${money(a.buffer_pence)}</span></div><div class="detail-line"><span>Daily spending allowance</span><span>${money(a.daily_allowance_pence)}</span></div><div class="detail-line"><span>Projected minimum</span><span class="${data.forecast.minima[a.id]<a.buffer_pence?'negative':''}">${money(data.forecast.minima[a.id])}</span></div><button data-action="edit-account" data-id="${a.id}">Update snapshot & preferences</button></section>`).join('')}</div>${!data.accounts.length?empty('Start with Barclays and Santander, then add the rest of your accounts.'):''}<p class="helper">GBP balances only in this version. Record foreign-currency accounts as a separately labelled GBP valuation. Credit-card debt is a negative balance; investments are manual valuations.</p>`;}
function spending(){return pageHeading('Understand your spending.','See what went where, without counting your own transfers twice.',periodSelect())+demoBanner()+`<div class="grid-two">${spendingPanel(true)}<section class="panel"><div class="panel-heading"><h2>Category breakdown</h2><button class="text-link" data-view="transactions">Edit categories ↗</button></div>${Object.entries(data.categories).map(([k,v],i)=>`<div class="legend-row"><i style="background:${colours[i%colours.length]}"></i><span>${esc(k)}</span><strong>${money(v)}</strong><span>${data.spending_pence>0?Math.round(v/data.spending_pence*100)+'%':'—'}</span></div>`).join('')||empty('No spending recorded for this month.')}<div class="panel-footnote">Categories come from your import and can be corrected in Transactions. Purchases on credit cards count here; repayments should be labelled transfers.</div></section></div>`;}
function forecastChart(){
  const accounts=data.accounts.filter(a=>a.kind==='current'), points=data.forecast.points;
  if(!accounts.length)return empty('Add a current account to see the balance forecast.');
  const vals=points.flatMap(p=>accounts.map(a=>p.balances[a.id])), low=Math.min(0,...vals), high=Math.max(10000,...vals), span=high-low;
  const width=window.matchMedia('(max-width:680px)').matches?340:800;
  const y=v=>190-(v-low)/span*160, x=i=>62+i/(points.length-1)*(width-90);
  return `<div class="forecast-legend">${accounts.map((a,i)=>`<span><i style="background:${colours[i%8]};display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px"></i>${esc(a.name)}</span>`).join('')}</div><svg class="forecast-chart" viewBox="0 0 ${width} 230" role="img" aria-label="Projected end-of-day current account balances"><g>${[low,(low+high)/2,high].map(v=>`<line x1="62" y1="${y(v)}" x2="${width-28}" y2="${y(v)}" stroke="#edf1eb"/><text x="0" y="${y(v)+4}">${esc(shortMoney(v))}</text>`).join('')}<line x1="62" y1="${y(0)}" x2="${width-28}" y2="${y(0)}" stroke="#d5b192" stroke-dasharray="4 4"/>${accounts.map((a,i)=>`<polyline fill="none" stroke="${colours[i%8]}" stroke-width="2.5" stroke-linejoin="round" points="${points.map((p,j)=>`${x(j)},${y(p.balances[a.id])}`).join(' ')}"/>`).join('')}<text x="62" y="222">Today</text><text x="${width-84}" y="222">${dateLabel(data.forecast.end)}</text></g></svg>`;
}
function cashflow(){return pageHeading('See what’s ahead.','A daily forecast built from your balances, planned payments and spending allowances.',`<select id="horizon" aria-label="Forecast horizon">${[14,30,60,90].map(d=>`<option value="${d}" ${d===days?'selected':''}>Next ${d} days</option>`).join('')}</select><button class="primary" data-action="add-schedule">＋ Planned payment</button>`)+demoBanner()+`<section class="panel wide-panel"><div class="panel-heading"><div><h2>Projected account balances</h2><p class="subtitle">No suggested transfers are applied to this forecast</p></div><span class="badge">Estimate</span></div>${forecastChart()}<div class="panel-footnote">${data.forecast.stale?'Some balance snapshots are stale. Refresh them before relying on the forecast. ':''}Expenses are processed before income on the same day. Minimum balances include intraday dips; lines show end-of-day balances. Today’s planned payments must still be outstanding. Daily allowances are additional to planned bills.</div></section><div class="grid-two">${upcomingPanel(true)}<section class="panel"><h2>Forecast assumptions</h2><p class="helper">Only payments you record appear here. Variable bills, pending card payments and unrecorded spending can change the outcome.</p><div class="table-wrap"><table><thead><tr><th>Account</th><th class="amount">Daily allowance</th><th class="amount">Minimum</th></tr></thead><tbody>${data.accounts.map(a=>`<tr><td>${esc(a.name)}</td><td class="amount">${money(a.daily_allowance_pence)}</td><td class="amount">${money(data.forecast.minima[a.id])}</td></tr>`).join('')}</tbody></table></div><p class="helper">Cash-flow headroom is the sum of each current account’s minimum, less its buffer, floored at zero. Savings and investments are excluded. It is a planning estimate, not guaranteed available spending.</p><button data-view="accounts">Adjust account assumptions</button></section></div>`;}
function plan(){return pageHeading('A plan. You make the moves.','Suggested top-ups to protect your account buffers. Nothing moves money here.',`<select id="horizon" aria-label="Forecast horizon">${[14,30,60,90].map(d=>`<option value="${d}" ${d===days?'selected':''}>Next ${d} days</option>`).join('')}</select>`)+demoBanner()+data.forecast.recommendations.map(r=>`<section class="plan-card"><div class="plan-top"><h2>Top up ${esc(r.name)}</h2><span class="badge" style="background:#f8e9d8;color:#9b713d">${r.stale?'Balance needs refreshing':'Plan by '+dateLabel(r.by_date)}</span></div><div class="plan-amount">${money(r.needed_pence)}</div><p class="subtitle">Total funding needed to maintain your buffer over the next ${days} days.</p><div class="plan-equation"><div>Projected minimum<b>${money(r.minimum_pence)}</b></div><div>Target buffer<b>${money(r.buffer_pence)}</b></div><div>First buffer breach<b>${dateLabel(r.breach_date)}</b></div></div>${r.sources.map(s=>`<div class="source"><span>${esc(s.name)} <span class="muted">→</span> ${esc(r.name)}</span><strong>${money(s.amount_pence)}</strong></div>`).join('')}${r.unfunded_pence>0?`<p class="note danger-note">${r.stale?'Update this account’s balance to get a source suggestion.':`${money(r.unfunded_pence)} still has no eligible funding source. Review your balances and upcoming payments; this plan is not fully funded.`}</p>`:''}<p class="helper">Source amounts reserve their own buffers and planned spending. Verify current available balances and transfer arrival times in your banking apps. The displayed deadline allows one calendar day, not a bank processing guarantee.</p><button data-action="explain" data-id="${r.account_id}">View calculation</button></section>`).join('')+(!data.forecast.recommendations.length?empty(data.accounts.length?'No projected current-account buffer shortfalls in this horizon. Keep your balance snapshots and planned payments up to date.':'Add accounts and planned bills to get funding suggestions.'):'')+`<div class="note">After making a transfer in your bank app, update both account snapshots and import or classify both transaction legs as transfers. Suggestions never mark a transfer as complete or change your balances.</div>`;}
function transactions(){return pageHeading('The story behind the numbers.','Search your history and keep spending categories accurate.',`${periodSelect()}<button class="primary" data-action="import">＋ Import CSV</button>`)+demoBanner()+`<section class="panel"><div class="toolbar"><input id="search" type="search" placeholder="Search descriptions or categories…" aria-label="Search transactions" value="${esc(search)}"><select id="account-filter" aria-label="Filter by account"><option value="">All accounts</option>${data.accounts.map(a=>`<option value="${a.id}" ${String(a.id)===filter?'selected':''}>${esc(a.name)}</option>`).join('')}</select><select id="kind-filter" aria-label="Filter transaction type"><option value="">All transaction types</option><option value="review" ${kindFilter==='review'?'selected':''}>Needs review</option>${['expense','income','transfer','adjustment'].map(k=>`<option ${k===kindFilter?'selected':''}>${k}</option>`).join('')}</select></div><div id="transaction-results">${transactionTable()}</div></section>`;}
function transactionTable(){const rows=data.transactions.filter(t=>(!filter||t.account_id===Number(filter))&&(!kindFilter||(kindFilter==='review'?t.needs_review:t.kind===kindFilter))&&`${t.description} ${t.category}`.toLowerCase().includes(search.toLowerCase()));return `<div class="table-wrap"><table><thead><tr><th>Date</th><th>Description</th><th>Account</th><th>Category</th><th>Type</th><th class="amount">Amount</th><th></th></tr></thead><tbody>${rows.map(t=>`<tr><td>${dateLabel(t.date)}</td><td>${esc(t.description)}</td><td>${esc(accountName(t.account_id))}</td><td>${esc(t.category)}</td><td><span class="pill">${t.kind}</span></td><td class="amount ${t.amount_pence>0?'positive':''}">${money(t.amount_pence)}</td><td><button class="text-link" data-action="classify" data-id="${t.id}" aria-label="Edit ${esc(t.description)} classification">Edit</button></td></tr>`).join('')}</tbody></table></div>${!rows.length?empty('No matching transactions for this month.'):''}<p class="helper">${rows.length} transactions · CSV imports update history only. Bank sync refreshes history and balances.</p>`;}
function dataPage(){return pageHeading('Your data. Your space.','Local records and read-only bank connections, in one place.')+demoBanner()+`<div class="data-grid"><section class="panel"><h2>Bring your finances into view</h2><p>Add accounts with a current GBP balance, then import your transaction history. CSV imports are previewed and checked for duplicate transaction IDs before anything is saved.</p><div class="toolbar"><button class="primary" data-action="add-account">Add account</button><button data-action="import">Import transactions</button></div><a href="/sample-transactions.csv" download>Download CSV template ↗</a><p>Required columns: <code>external_id, date, description, amount, category, kind</code>. Use YYYY-MM-DD dates, signed GBP amounts, and stable IDs unique within each account.</p></section><section class="panel"><h2>Bank connections</h2><p><span class="badge">Connection setup available</span></p><p>A real Enable Banking account-information connector is available. Register your production application, approve bank consent, then sync balances and transactions into your personal workspace.</p><p>Bank passwords stay with your bank. SmartMoney has no payment or transfer execution endpoints. <button data-action="bank-setup" class="primary">Set up real bank connections →</button></p></section><section class="panel"><h2>App & local storage</h2><p>Use the same dashboard in your browser or install it as an app in a supported browser. Keep the Python server running while using either.</p><button data-action="install-help">How to install</button><p>Your records are in SQLite files on the computer running the Python backend. They are not encrypted by this app. Use your operating system’s disk encryption and keep backups private.</p><p>Phone access uses the server’s configured private HTTPS address. Local-only setups can be reached through an SSH tunnel.</p></section><section class="panel"><h2>Make forecasts useful</h2><p>1. Refresh account balances daily before using suggestions.<br>2. Record only future or still-outstanding payments.<br>3. Set a daily allowance for spending outside planned bills.<br>4. Mark internal transfers and card repayments as transfers.<br>5. Confirm live balances in your banking apps before acting.</p><button data-view="cashflow">Review planned payments →</button></section></div>`;}
function showDialog(title,content){$('#dialog-content').innerHTML=`<div class="dialog-heading"><h2>${title}</h2><button data-action="close-dialog" aria-label="Close dialog">×</button></div>${content}`;$('#dialog').showModal();}
function field(label,name,value='',type='text',extra=''){return `<label class="field">${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;}
function select(label,name,options,value){return `<label class="field">${label}<select name="${name}">${options.map(([k,v])=>`<option value="${esc(k)}" ${String(k)===String(value)?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`;}
function formEnd(label='Save local record'){return `<div class="form-error" role="alert"></div><div class="form-actions"><button type="button" data-action="close-dialog">Cancel</button><button class="primary" type="submit">${label}</button></div></form>`;}
function accountForm(id){
  const a=data.accounts.find(a=>a.id===id);
  showDialog(a?'Update account snapshot':'Add an account',`<form id="account-form" data-id="${id||''}"><div class="form-grid">${field('Account name','name',a?.name||'','text','required maxlength="80"')}${field('Bank / institution','institution',a?.institution||'','text','required maxlength="80"')}${select('Type','kind',['current','savings','credit','investment'].map(k=>[k,k]),a?.kind||'current')}${field('Purpose','role',a?.role||'','text','maxlength="100"')}${field('Current balance (£)','balance',a?(a.balance_pence/100).toFixed(2):'','number','required step="0.01"')}${field('Balance as of','balance_as_of',a?.balance_as_of||data.today,'date',`required max="${data.today}"`)}${field('Safety buffer (£)','buffer',a?(a.buffer_pence/100).toFixed(2):'0','number','required min="0" step="0.01"')}${field('Daily spending allowance (£)','daily_allowance',a?(a.daily_allowance_pence/100).toFixed(2):'0','number','required min="0" step="0.01"')}<label class="check-field full"><input type="checkbox" name="can_fund" ${a?.can_fund?'checked':''}>Allow this current account to fund transfer suggestions</label></div><p class="helper">This records a local snapshot; it does not alter your bank account. Daily allowance covers spending beyond planned bills. Enter credit-card debt as a negative number.</p>${formEnd()}`);
}
function scheduleForm(){
  if(!data.accounts.length){toast('Add an account first.');return;}
  showDialog('Plan an upcoming payment',`<form id="schedule-form"><div class="form-grid">${field('Payment name','name','','text','required maxlength="100"')}${select('Account','account_id',data.accounts.map(a=>[a.id,a.name]),data.accounts[0].id)}${select('Type','kind',[['expense','Bill / expense'],['income','Income'],['transfer','Internal transfer']], 'expense')}${field('Amount (£, negative for outgoing)','amount','','number','required step="0.01"')}${field('Next due date','next_due',data.today,'date',`required min="${data.today}"`)}${select('Repeat','frequency',[['monthly','Monthly'],['once','One-off']],'monthly')}${select('Destination (transfers only)','target_account_id',[['','None'],...data.accounts.map(a=>[a.id,a.name])],'')}</div><p class="helper">Add only payments still outstanding. An entry due today is applied on top of today’s balance snapshot. Monthly payments repeat on the original day, clamped for shorter months.</p>${formEnd('Save planned payment')}`);
}
function importForm(){
  if(!data.accounts.length){showDialog('Start with an account',`<p class="helper">Create the account this transaction history belongs to, then import its CSV.</p><button class="primary" data-action="add-account">Add account</button>`);return;}
  showDialog('Import transaction history',`<form id="import-form">${select('Import into account','account_id',data.accounts.map(a=>[a.id,a.name]),data.accounts[0].id)}<p class="helper">Use the <a href="/sample-transactions.csv" download>CSV template</a>. Imports affect transaction history only; record your current balance separately. CSV data is sent only to your SmartMoney backend.</p><label class="field">Choose a CSV file<input type="file" id="csv-file" accept=".csv,text/csv"></label><p class="helper">Or paste CSV below:</p><textarea name="csv_text" required aria-label="CSV contents" placeholder="external_id,date,description,amount,category,kind"></textarea><div id="preview" class="import-preview"></div><div class="form-error" role="alert"></div><div class="form-actions"><button type="button" data-action="close-dialog">Cancel</button><button type="submit" class="primary" id="import-submit">Preview import</button></div></form>`);
}
function classifyForm(id){const t=data.transactions.find(t=>t.id===id);showDialog('Correct transaction classification',`<form id="classify-form" data-id="${id}"><p class="helper">${esc(t.description)} · ${money(t.amount_pence)}</p><div class="form-grid">${field('Category','category',t.category,'text','required maxlength="60"')}${select('Type','kind',['expense','income','transfer','adjustment'].map(k=>[k,k]),t.kind)}</div><p class="helper">Use transfer for movements between your accounts, including credit-card repayments. Use expense for card purchases and refunds. Use adjustment for valuation changes.</p>${formEnd('Save classification')}`);}
function installHelp(){showDialog('SmartMoney as an app',`<p class="helper">Open this app’s configured HTTPS address in Chrome on Android, or Edge or Chrome on your computer. For an SSH tunnel, use <strong>http://127.0.0.1:8765</strong>. Use the install icon in the address bar, or the browser menu’s app installation option. SmartMoney then opens in its own app window.</p><div class="note">Keep the Python server running. Your app reads live local data; financial records are not cached for offline use.</div><p class="helper">Phone access requires the private HTTPS setup described in the Raspberry Pi guide. Keep the server awake and your private network connected.</p>`);}
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.view){nav(button.dataset.view);return;}
  const action=button.dataset.action,id=Number(button.dataset.id);
  if(action==='close-dialog')$('#dialog').close();
  if(action==='refresh')refresh();
  if(action==='bank-setup'){location.assign('/connections.html');return;}
  if(action==='review-imports'){
    kindFilter='review';filter='';search='';
    month=data.unreviewed_months[0]||month;view='transactions';location.hash=view;refresh();
  }
  if(action==='personal'){$('#dataset').value='personal';dataset='personal';rememberWorkspace();month='';search='';filter='';refresh();}
  if(action==='add-account'){$('#dialog').close();accountForm();}
  if(action==='edit-account')accountForm(id);
  if(action==='add-schedule')scheduleForm();
  if(action==='import')importForm();
  if(action==='classify')classifyForm(id);
  if(action==='install-help')installHelp();
  if(action==='remove-schedule'){
    const s=data.schedules.find(s=>s.id===id);
    showDialog('Remove planned payment?',`<p class="helper">Remove ${esc(s.name)} and all its future occurrences from the forecast? This affects your local plan only.</p><div class="form-actions"><button data-action="close-dialog">Keep it</button><button class="primary" data-action="confirm-remove" data-id="${id}">Remove from plan</button></div>`);
  }
  if(action==='confirm-remove'){try{await api('schedules/'+id,{method:'DELETE'});$('#dialog').close();await refresh();toast('Planned payment removed.');}catch(e){toast(e.message);}}
  if(action==='explain'){
    const r=data.forecast.recommendations.find(r=>r.account_id===id),a=data.accounts.find(a=>a.id===id);
    showDialog('How this suggestion is calculated',`<p class="helper">${esc(a.name)} starts at ${money(a.forecast_balance_pence ?? a.balance_pence)}. We apply recorded payments and ${money(a.daily_allowance_pence)} per day in spending allowances across the forecast.</p><div class="note">Buffer ${money(r.buffer_pence)} − projected minimum ${money(r.minimum_pence)} = funding needed ${money(r.needed_pence)}</div><p class="helper">Funding sources must be current accounts you opted in, with today’s balance snapshot. Suggested amounts are limited by each source’s lowest projected balance minus its buffer. Capacity already allocated to another suggestion cannot be used again. Same-day outgoings are processed before income.</p><p class="helper">The forecast does not assume you follow this suggestion. Refresh balances after transferring in your banking app.</p>`);
  }
});
document.addEventListener('change',async event=>{
  if(event.target.id==='dataset'){dataset=event.target.value;rememberWorkspace();month='';search='';filter='';kindFilter='';$('#dialog').close();await refresh();}
  if(event.target.id==='month'){month=event.target.value;await refresh();}
  if(event.target.id==='horizon'){days=Number(event.target.value);await refresh();}
  if(event.target.id==='account-filter'){filter=event.target.value;$('#transaction-results').innerHTML=transactionTable();}
  if(event.target.id==='kind-filter'){kindFilter=event.target.value;$('#transaction-results').innerHTML=transactionTable();}
  if(event.target.id==='csv-file'){
    const file=event.target.files[0];if(!file)return;
    if(file.size>1_500_000){toast('Choose a CSV smaller than 1.5 MB.');return;}
    const form=$('#import-form');$('textarea',form).value=await file.text();invalidatePreview(form);
  }
  if(event.target.closest('#import-form')&&event.target.name==='account_id')invalidatePreview($('#import-form'));
});
function invalidatePreview(form){delete form.dataset.preview;$('#preview').innerHTML='';$('#import-submit').textContent='Preview import';}
document.addEventListener('input',event=>{
  if(event.target.id==='search'){search=event.target.value;$('#transaction-results').innerHTML=transactionTable();}
  if(event.target.name==='csv_text')invalidatePreview($('#import-form'));
});
document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.closest('#dialog'))return;event.preventDefault();
  const values=Object.fromEntries(new FormData(form)), submit=$('button[type=submit]',form), error=$('.form-error',form);
  submit.disabled=true;error.textContent='';
  try{
    if(form.id==='account-form'){
      values.can_fund=form.elements.can_fund.checked;
      await api('accounts'+(form.dataset.id?'/'+form.dataset.id:''),{method:form.dataset.id?'PUT':'POST',body:JSON.stringify(values)});
    }else if(form.id==='schedule-form'){
      values.account_id=Number(values.account_id);values.target_account_id=values.target_account_id?Number(values.target_account_id):null;
      await api('schedules',{method:'POST',body:JSON.stringify(values)});
    }else if(form.id==='classify-form'){
      await api('transactions/'+form.dataset.id,{method:'PATCH',body:JSON.stringify(values)});
    }else if(form.id==='import-form'){
      values.account_id=Number(values.account_id);
      if(!form.dataset.preview){
        const result=await api('import/preview',{method:'POST',body:JSON.stringify(values)});
        $('#preview').innerHTML=`<div class="note">${result.new_count} new transactions · ${result.duplicates} already imported</div><div class="table-wrap"><table><tbody>${result.rows.map(r=>`<tr><td>${dateLabel(r.date)}</td><td>${esc(r.description)}</td><td>${esc(r.kind)}</td><td>${money(r.amount_pence)}</td></tr>`).join('')}</tbody></table></div><p class="helper">Showing up to 20 preview rows. Review classifications, especially internal transfers.</p>`;
        form.dataset.preview='yes';submit.textContent='Import '+result.new_count+' transactions';return;
      }
      const result=await api('import/commit',{method:'POST',body:JSON.stringify(values)});
      toast(result.imported+' transactions imported. Balance snapshots are unchanged.');
    }
    $('#dialog').close();await refresh();if(form.id!=='import-form')toast('Saved in your '+(dataset==='demo'?'demo':'personal')+' workspace.');
  }catch(e){error.textContent=e.message;}finally{submit.disabled=false;}
});
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(titles[next]&&next!==view){view=next;render();}});
window.matchMedia('(max-width:680px)').addEventListener('change',()=>{if(!$('#dialog').open)render();});
window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;});
$('#install').addEventListener('click',async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;}else installHelp();});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
refresh();
