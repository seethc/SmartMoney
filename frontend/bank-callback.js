'use strict';
const query=new URLSearchParams(location.search);
const payload={code:query.get('code')||'',state:query.get('state')||'',error:query.get('error')||''};
history.replaceState(null,'','/openbanking-callback');
(async()=>{
  try{
    if(!payload.state)throw new Error('No bank consent response was supplied. Start from Bank connections.');
    const response=await fetch('/api/openbanking/complete?dataset=personal',{method:'POST',headers:{'Content-Type':'application/json','X-SmartMoney':'local'},body:JSON.stringify(payload),cache:'no-store'});
    const result=await response.json();
    if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'Consent could not be completed. Please start again.');
    document.querySelector('#status-heading').textContent='Bank connected.';
    document.querySelector('#status-message').textContent=`${result.bank} authorised ${result.accounts} accounts. Return to Bank connections and select Sync now to import real balances and transactions.`;
  }catch(e){document.querySelector('#status-heading').textContent='Connection needs attention';document.querySelector('#status-message').textContent=e.message;}
})();
