/* olap.js */
const OLAP_HINTS={'roll-up':'ROLL-UP: Hour → Day → Month (aggregate up).','drill-down':'DRILL-DOWN: Month → Day → Hour (more detail).','slice':'SLICE: fix one dimension, e.g. _traffic=Jam.','dice':'DICE: filter 2+ dims, e.g. city + traffic.','pivot':'PIVOT: rows × columns matrix for a metric.'};
let olapInit=false;
async function initOlap(){
 document.getElementById('olapHint').textContent=OLAP_HINTS[document.getElementById('olapOp').value];
 document.getElementById('olapOp').onchange=e=>document.getElementById('olapHint').textContent=OLAP_HINTS[e.target.value];
 if(olapInit)return;olapInit=true;
 try{const m=await api('/api/olap');
  const fill=(id,vals)=>document.getElementById(id).innerHTML=vals.map(v=>`<option>${v}</option>`).join('');
  fill('olapDim',m.dimensions);fill('olapRows',m.dimensions);fill('olapCols',m.dimensions);fill('olapMetric',m.metrics);
  document.getElementById('olapRun').onclick=runOlap;runOlap();
 }catch(e){toast(e.message)}
}
async function runOlap(){
 const filters={};document.getElementById('olapFilters').value.split('\n').forEach(l=>{const[k,v]=l.split('=').map(s=>s?.trim());if(k&&v)filters[k]=v;});
 const body={op:document.getElementById('olapOp').value,dimension:document.getElementById('olapDim').value,rows:document.getElementById('olapRows').value,columns:document.getElementById('olapCols').value,metric:document.getElementById('olapMetric').value,filters};
 try{const j=await api('/api/olap',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(j.error){toast(j.error);return;}
  document.getElementById('olapOpName').textContent=j.operation;document.getElementById('olapExpl').textContent=j.explanation||'';
  const rows=j.chart||[];bar('olapChart',rows,'#4f46e5');
  const t=document.getElementById('olapTable');
  if(j.operation==='pivot'&&j.table.length){const cols=Object.keys(j.table[0]);t.querySelector('thead').innerHTML='<tr>'+cols.map(c=>`<th>${c}</th>`).join('')+'</tr>';t.querySelector('tbody').innerHTML=j.table.map(r=>'<tr>'+cols.map(c=>`<td>${r[c]}</td>`).join('')+'</tr>').join('');}
  else{t.querySelector('thead').innerHTML='<tr><th>Label</th><th>Value</th></tr>';t.querySelector('tbody').innerHTML=(j.table||[]).map(r=>`<tr><td>${r.label}</td><td>${r.value}</td></tr>`).join('');}
 }catch(e){toast('OLAP: '+e.message)}
}
