/* live.js — live restaurant listings (separate from historical analytics) */
let liveInit=false;
function initLive(){
 if(liveInit)return;liveInit=true;
 document.getElementById('liveBtn').onclick=fetchLive;
 refreshLiveStatus();
}
async function refreshLiveStatus(){
 try{
  const j=await api('/api/live-status');
  const sel=document.getElementById('liveArea');
  if(!sel.options.length)sel.innerHTML=(j.areas||[]).map(a=>`<option value="${a.id}">${a.label}</option>`).join('');
  document.getElementById('liveStatus').textContent=
   `Provider: ${j.provider} · Mode: ${j.mode} · Historical rows: ${(j.historical_rows??0).toLocaleString()}${j.last_refresh?` · Last live fetch: ${j.last_refresh} (${j.live_records} records)`:''} · ${j.reason||''}`;
 }catch(e){document.getElementById('liveStatus').textContent=e.message;}
}
async function fetchLive(){
 const out=document.getElementById('liveOut'),meta=document.getElementById('liveMeta');
 out.innerHTML='<div class="empty">Fetching live data…</div>';meta.textContent='';
 try{
  const j=await api('/api/live-fetch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({area:document.getElementById('liveArea').value})});
  if(!j.available){out.innerHTML=`<div class="empty">${j.reason||'Live fetch unavailable.'}</div>`;return;}
  meta.textContent=`${j.record_count} live records · ${j.fetched_at}${j.cached?' · cached':''}`;
  out.innerHTML=`<div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Cuisine</th><th>Hours</th><th>Lat</th><th>Lon</th></tr></thead><tbody>`
   +((j.records||[]).map(r=>`<tr><td>${r.name??'—'}</td><td>${r.category??'—'}</td><td>${r.cuisine??'—'}</td><td>${r.opening_hours??'—'}</td><td>${r.lat??'—'}</td><td>${r.lon??'—'}</td></tr>`).join('')||'<tr><td colspan="6">No records returned.</td></tr>')+`</tbody></table></div>`
   +`<p class="hint">Source: ${j.source} · ${j.data_type}. Historical delivery analytics are unchanged.</p>`;
  refreshLiveStatus();
 }catch(e){out.innerHTML=`<div class="empty">${e.message}</div>`;}
}
