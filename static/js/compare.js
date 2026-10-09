/* compare.js — algorithm comparison (values computed live by backend) */
let cmpInit=false,cmpCat='classification';
const CMPC=['#4f46e5','#10b981','#f59e0b','#ec4899'];
function initCompare(){
 document.querySelectorAll('#cmpTabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#cmpTabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');cmpCat=b.dataset.t;loadCompare();});
 if(cmpInit)return;cmpInit=true;loadCompare();
}
function cmpTable(head,rows){return `<div class="table-wrap"><table><thead><tr>${head.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c??'—'}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
function cmpBars(id,labels,datasets){mkChart(id,{type:'bar',data:{labels:labels,datasets:datasets.map((d,i)=>({label:d.label,data:d.data,backgroundColor:CMPC[i%4],borderRadius:6}))},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true}}}});}
async function loadCompare(){
 const out=document.getElementById('cmpOut'),note=document.getElementById('cmpNote');
 out.innerHTML='<div class="empty">Running comparison… (first run trains models, results are cached after that)</div>';note.textContent='';
 try{
  const j=await api('/api/algorithm-comparison?category='+cmpCat);
  if(j.error){out.innerHTML=`<div class="empty">${j.error}</div>`;return;}
  note.textContent=(j.note||'')+(j.cached?' · cached result':' · freshly computed');
  if(cmpCat==='classification')cmpClass(j);else if(cmpCat==='clustering')cmpClust(j);
  else if(cmpCat==='association')cmpAssoc(j);else cmpAnom(j);
 }catch(e){out.innerHTML=`<div class="empty">${e.message}</div>`;}
}
function cmpClass(j){
 const ms=j.models||[],names=ms.map(m=>m.name);
 cmpBars('cmpChart',names,['accuracy','precision','recall','f1'].map(k=>({label:k,data:ms.map(m=>m[k]??0)})));
 cmpBars('cmpChart2',names,[{label:'train s',data:ms.map(m=>m.train_time_s??0)},{label:'predict s',data:ms.map(m=>m.predict_time_s??0)}]);
 const b=j.class_balance_test||{};
 document.getElementById('cmpOut').innerHTML=cmpTable(['Model','Acc','Prec','Rec','F1','ROC-AUC','Train s','Predict s'],
  ms.map(m=>[m.name,m.accuracy,m.precision,m.recall,m.f1,m.roc_auc,m.train_time_s,m.predict_time_s]))
  +`<p class="hint">Target ${j.target} · ${j.split} (seed ${j.random_state}) · test delayed ${b.delayed_pct}% · n_train ${b.n_train} / n_test ${b.n_test} · features ${j.features}. Production predictor unchanged.</p>`
  +ms.filter(m=>m.confusion_matrix).map(m=>`<p class="hint">${m.name} confusion matrix: [${m.confusion_matrix[0]}] / [${m.confusion_matrix[1]}]</p>`).join('');
}
function cmpClust(j){
 const as=j.algorithms||[],names=as.map(a=>a.name);
 cmpBars('cmpChart',names,[{label:'silhouette (higher better)',data:as.map(a=>a.silhouette??0)}]);
 cmpBars('cmpChart2',names,[{label:'runtime s',data:as.map(a=>a.runtime_s??0)}]);
 document.getElementById('cmpOut').innerHTML=cmpTable(['Algorithm','Clusters','Silhouette','Davies-Bouldin','Calinski-Harabasz','Noise %','Runtime s'],
  as.map(a=>[a.name,a.n_clusters,a.silhouette,a.davies_bouldin,a.calinski_harabasz,a.noise_pct,a.runtime_s]))
  +`<p class="hint">k=${j.k} · features ${j.features} · sample n=${j.sample_n} (seed ${j.random_state}). Structure metrics only, not business success. ${as.map(a=>a.metric_note||'').filter(Boolean).join(' ')}</p>`;
}
function cmpAssoc(j){
 const as=j.algorithms||[],names=as.map(a=>a.name),p=j.params||{};
 cmpBars('cmpChart',names,[{label:'rules',data:as.map(a=>a.n_rules??0)}]);
 cmpBars('cmpChart2',names,[{label:'runtime s',data:as.map(a=>a.runtime_s??0)}]);
 document.getElementById('cmpOut').innerHTML=cmpTable(['Miner','Rules','Avg support','Avg confidence','Avg lift','Runtime s'],
  as.map(a=>[a.name,a.n_rules,a.avg_support,a.avg_confidence,a.avg_lift,a.runtime_s]))
  +`<p class="hint">min_support ${p.min_support} · min_confidence ${p.min_confidence} · max_len ${p.max_len} · transactions ${p.transactions} · items ${p.items} · sample ${p.sample_n} (seed ${p.random_state}). Association is not causation.</p>`
  +as.filter(a=>a.top_rules).map(a=>`<p class="hint"><b>${a.name} top rules:</b><br>${a.top_rules.join('<br>')}</p>`).join('');
}
function cmpAnom(j){
 const ds=j.detectors||[],names=ds.map(d=>d.name);
 cmpBars('cmpChart',names,[{label:'anomaly %',data:ds.map(d=>d.anomaly_pct??0)}]);
 cmpBars('cmpChart2',names,[{label:'runtime s',data:ds.map(d=>d.runtime_s??0)}]);
 document.getElementById('cmpOut').innerHTML=cmpTable(['Detector','Flagged','Anomaly %','Runtime s'],
  ds.map(d=>[d.name,d.n_anomalies,d.anomaly_pct,d.runtime_s]))
  +`<p class="hint">Features ${j.features} · contamination ${j.contamination} · n=${j.sample_n} · detector agreement (Jaccard) ${j.agreement_jaccard??'—'}. No ground-truth labels: agreement is overlap, not accuracy.</p>`;
}
