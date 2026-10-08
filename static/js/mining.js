/* mining.js — tabs + 4 techniques */
let mineInit=false;
function initMining(){
 document.querySelectorAll('#mineTabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#mineTabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');document.querySelectorAll('.mine-pane').forEach(p=>p.classList.toggle('hidden',p.dataset.p!==b.dataset.t));});
 if(mineInit)return;mineInit=true;
 document.getElementById('mineBtn').onclick=async()=>{try{const j=await api('/api/association-rules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({min_support:+document.getElementById('minSup').value,min_confidence:+document.getElementById('minConf').value})});
  document.getElementById('rulesOut').innerHTML=(j.rules||[]).map(r=>`<div class="rule"><div class="pat">IF ${r.antecedent.join(' + ')} → THEN ${r.consequent.join(' + ')}</div><div class="mets"><span class="met">support ${r.support}</span><span class="met">confidence ${r.confidence}</span><span class="met">lift ${r.lift}</span></div></div>`).join('')||`<div class="empty">${j.message||'No rules'}</div>`;}catch(e){toast(e.message)}};
 document.getElementById('clBtn').onclick=async()=>{try{const j=await api('/api/clusters',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({k:+document.getElementById('kVal').value})});
  if(j.error){toast(j.error);return;}
  document.getElementById('clOut').innerHTML='<div class="kpis">'+j.clusters.map(c=>`<div class="kpi"><div class="l">${c.name}</div><div class="v">${c.count}</div><div class="d">avg ${c.avg_time} min · ${c.avg_distance} km · delay ${c.delay_rate}%</div></div>`).join('')+'</div>';
  const cols=['#4f46e5','#10b981','#f59e0b','#ec4899','#0ea5e9','#7c3aed','#dc2626','#16a34a'];
  mkChart('clChart',{type:'scatter',data:{datasets:j.clusters.map((c,i)=>({label:c.name,data:(j.points||[]).filter(p=>p.c===c.id).map(p=>({x:p.x,y:p.y})),backgroundColor:cols[i%8]}))},options:{responsive:true,maintainAspectRatio:false,scales:{x:{title:{display:true,text:'distance'}},y:{title:{display:true,text:'time'}}}}});
 }catch(e){toast(e.message)}};
 document.getElementById('cfBtn').onclick=async()=>{try{const j=await api('/api/classification');
  if(j.error){toast(j.error);return;}
  document.getElementById('cfOut').innerHTML=`<div class="kpis">${['accuracy','precision','recall','f1'].map(k=>`<div class="kpi"><div class="l">${k}</div><div class="v">${j[k]}</div></div>`).join('')}</div><p class="hint">Confusion matrix: [${j.confusion_matrix[0]}] / [${j.confusion_matrix[1]}] · train ${j.n_train} / test ${j.n_test} ${j.cached?'(cached)':''}</p><p><b>Top features:</b> ${(j.features||[]).slice(0,8).map(f=>f.feature+' ('+f.importance+')').join(', ')}</p>`;
  bar('cfChart',(j.features||[]).slice(0,10).map(f=>({label:f.feature,value:f.importance})),'#16a34a');
 }catch(e){toast(e.message)}};
 document.getElementById('anBtn').onclick=async()=>{try{const j=await api('/api/anomalies?limit=60');
  document.querySelector('#anTable tbody').innerHTML=(j.anomalies||[]).map(a=>`<tr><td>${a.order_id}</td><td>${a.distance}</td><td>${a.delivery_time}</td><td>${a.expected??'—'}</td><td>${a.deviation??'—'}</td><td>${a.note}</td></tr>`).join('');}catch(e){toast(e.message)}};
 document.getElementById('mineBtn').click();
}
