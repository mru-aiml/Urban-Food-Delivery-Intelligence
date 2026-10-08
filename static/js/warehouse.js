/* warehouse.js — schema viz, ETL, quality, explorer */
async function loadWh(){
 try{const j=await api('/api/warehouse/schema');
  document.getElementById('schemaViz').innerHTML=j.tables.map(t=>`<div class="tbl ${t.type}" onclick='showTbl(${JSON.stringify(t.name)})'>${t.name}<div style="font-size:11px;font-weight:400">${t.type}</div></div>`).join('');
  window._tables={};j.tables.forEach(t=>window._tables[t.name]=t);
  const e=j.etl||{};document.getElementById('etlPipe').innerHTML=['RAW DATA','EXTRACT','TRANSFORM','CLEAN','LOAD','DATA WAREHOUSE','ANALYTICS'].map(s=>`<span class="estep">${s}</span>`).join('<span class="earr">↓</span>')+`<div class="kv" style="margin-top:10px"><b>Rows loaded</b><span>${e.rows_loaded??'—'}</span><b>Duplicates</b><span>${e.duplicates_removed??'—'}</span><b>Invalid</b><span>${e.invalid_values_flagged??'—'}</span><b>Final</b><span>${e.final_usable_records??'—'}</span><b>Started</b><span>${e.started_at??''}</span><b>MySQL</b><span>${j.mysql.available?'connected':'offline — file-backed warehouse ('+j.mysql.detail.slice(0,60)+')'}</span></div>`;
 }catch(e){toast(e.message)}
}
function showTbl(n){const t=window._tables[n];document.getElementById('schemaDetail').innerHTML=`<div class="card"><div class="card-h">${t.name}</div><p class="hint">${t.description}</p><p>${t.columns.map(c=>`<span class="met">${c}</span>`).join(' ')}</p></div>`;}
let exPage=1;
async function loadExplorer(){
 const q=sessionStorage.getItem('q')||document.getElementById('exQ').value;sessionStorage.removeItem('q');document.getElementById('exQ').value=q||'';
 const band=sessionStorage.getItem('band')||document.getElementById('exBand').value;sessionStorage.removeItem('band');if(band)document.getElementById('exBand').value=band;
 try{const j=await api(`/api/orders?page=${exPage}&size=20&q=${encodeURIComponent(q||'')}&band=${encodeURIComponent(band||'all')}`);
  document.getElementById('exInfo').textContent=`${j.total.toLocaleString()} rows · ${j.columns.length} cols`;
  document.getElementById('exPage').textContent=`Page ${j.page}/${j.pages}`;
  const t=document.getElementById('exTable');t.querySelector('thead').innerHTML='<tr>'+j.columns.map(c=>`<th>${c}</th>`).join('')+'</tr>';
  t.querySelector('tbody').innerHTML=j.rows.map(r=>'<tr>'+j.columns.map(c=>`<td>${r[c]??''}</td>`).join('')+'</tr>').join('')||'<tr><td>No rows</td></tr>';
 }catch(e){toast(e.message)}
}
document.addEventListener('DOMContentLoaded',()=>{
 document.getElementById('exBtn').onclick=()=>{exPage=1;loadExplorer();};
 document.getElementById('exPrev').onclick=()=>{exPage=Math.max(1,exPage-1);loadExplorer();};
 document.getElementById('exNext').onclick=()=>{exPage++;loadExplorer();};
 document.getElementById('dqBtn').onclick=async()=>{try{const j=await api('/api/data-quality');
  document.getElementById('dqScore').innerHTML=`<span class="pill">Quality Score ${j.score}/100</span>`;
  document.getElementById('dqOut').innerHTML=`<div class="kpis">${Object.entries(j.dimensions).map(([k,v])=>`<div class="kpi"><div class="l">${k}</div><div class="v">${v}%</div></div>`).join('')}</div><p class="hint">Duplicates: ${j.duplicate_rows} · Missing cells: ${j.missing_total} · Raw ${j.raw_rows} → Clean ${j.clean_rows}</p><div class="table-wrap"><table><thead><tr><th>Column</th><th>Missing</th><th>Type</th></tr></thead><tbody>${Object.keys(j.missing_by_column).map(c=>`<tr><td>${c}</td><td>${j.missing_by_column[c]}</td><td>${j.dtypes[c]}</td></tr>`).join('')}</tbody></table></div>`;}catch(e){toast(e.message)}};
});
