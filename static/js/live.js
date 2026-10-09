/* live.js — live restaurant listings (separate from historical analytics) */
let liveInit=false,fetching=false;
let LIVE_TIMEOUT_MS=90000;
/* Frontend-only example rows. Never sent to the API, never presented as live
   results — always rendered under the "Sample preview" label. */
const SAMPLE_PREVIEW=[
 {name:'Sharma Snacks Corner',category:'restaurant',cuisine:'north indian',hours:'Mo-Su 11:00-23:00'},
 {name:'Coastal Spice House',category:'restaurant',cuisine:'seafood; south indian',hours:'Mo-Su 12:00-22:30'},
 {name:'Green Bowl Cafe',category:'restaurant',cuisine:'healthy; continental',hours:'Mo-Sa 09:00-21:00'},
 {name:'Midnight Biryani Express',category:'fast_food',cuisine:'biryani; mughlai',hours:'Mo-Su 11:00-23:59'},
 {name:'Filter Coffee Works',category:'restaurant',cuisine:'cafe; south indian',hours:'Mo-Su 08:00-22:00'},
 {name:'Chaat Chowk',category:'fast_food',cuisine:'chaat; street food',hours:'Tu-Su 12:00-22:00'}
];
function esc(s){return String(s??'—').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function previewTableHTML(area){
 const rows=SAMPLE_PREVIEW.map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(r.cuisine)} (${esc(r.category)})</td><td>${esc(area)}</td><td>${esc(r.hours)}</td><td>Sample preview</td></tr>`).join('');
 return `<p class="hint"><b>Sample preview — waiting for live API response.</b> These example rows are placeholders, not verified live results.</p><div class="table-wrap"><table><thead><tr><th>Restaurant Name</th><th>Cuisine/Category</th><th>Area</th><th>Opening Hours</th><th>Data Source</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function resultsTableHTML(j){
 const rows=((j.records||[]).map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(r.category)}</td><td>${esc(r.cuisine)}</td><td>${esc(r.opening_hours)}</td><td>${esc(r.lat)}</td><td>${esc(r.lon)}</td></tr>`).join('')
  ||'<tr><td colspan="6">No live records returned for this area right now. Try another area or retry.</td></tr>');
 return `<p class="hint"><b>Live restaurant listings (OpenStreetMap) — not delivery orders.</b></p><div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Cuisine</th><th>Hours</th><th>Lat</th><th>Lon</th></tr></thead><tbody>${rows}</tbody></table></div>`
  +`<p class="hint">Source: ${esc(j.source)} · ${esc(j.data_type)}. Historical delivery analytics are unchanged.</p>`;
}
function fetchErrorText(e){
 if(e&&(e.name==='AbortError'||/abort/i.test(e.message||'')))return 'Request timed out. The sample preview is retained — please retry.';
 const st=e&&e.status,body=(e&&e.body)||{};
 if(st===429){const s=body.retry_after_seconds!=null?` Please wait about ${body.retry_after_seconds}s and retry.`:' Please wait about a minute and retry.';return 'Too many requests.'+s+' The sample preview is retained.';}
 const reason=body.reason||(e&&e.message)||'request failed';
 return `Live fetch failed (${reason}). The sample preview is retained — please retry.`;
}
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
 if(fetching)return;fetching=true;
 const btn=document.getElementById('liveBtn');btn.disabled=true;
 const out=document.getElementById('liveOut'),meta=document.getElementById('liveMeta');
 const sel=document.getElementById('liveArea'),area=sel.value;
 const areaLabel=(sel.options[sel.selectedIndex]||{}).text||area;
 out.innerHTML=`<p class="hint"><span class="spin"></span>Fetching live data…</p>`+previewTableHTML(areaLabel);
 meta.textContent='';
 const ctrl=new AbortController();const to=setTimeout(()=>ctrl.abort(),LIVE_TIMEOUT_MS);
 try{
  const r=await fetch('/api/live-fetch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({area}),signal:ctrl.signal});
  let j=null;try{j=await r.json();}catch(_){j=null;}
  if(!r.ok||!j||!j.available)throw{status:r.status,body:j,message:(j&&(j.reason||j.error))||r.statusText};
  meta.textContent=`${j.record_count} live records · ${j.fetched_at}${j.cached?' · cached':''}`;
  out.innerHTML=resultsTableHTML(j);
  refreshLiveStatus();
 }catch(e){
  out.innerHTML=`<div class="empty">${esc(fetchErrorText(e))}</div>`+previewTableHTML(areaLabel);
 }finally{clearTimeout(to);fetching=false;btn.disabled=false;}
}
