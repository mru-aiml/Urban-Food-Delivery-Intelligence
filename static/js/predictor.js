/* predictor.js — risk form + why-late */
const FIELDS=[['distance','number','Distance (km)',5],['hour','number','Hour (0-23)',19],['multiple_deliveries','number','Multiple deliveries',1],['rating','number','Courier rating',4.5],['traffic','select','Traffic',['Jam','High','Medium','Low']],['weather','select','Weather',['Sunny','Cloudy','Windy','Fog','Stormy','Sandstorms']],['vehicle','select','Vehicle',['motorcycle','scooter','electric_scooter','bicycle']],['order_type','select','Order type',['Snack','Meal','Drinks','Buffet']],['city','select','City',['Metropolitian','Urban','Semi-Urban']]];
function buildForm(el,vals){document.getElementById(el).innerHTML=FIELDS.map(([k,t,l,d])=>t==='select'?`<label>${l}<select data-k="${k}">${d.map(o=>`<option ${vals&&vals[k]===o?'selected':''}>${o}</option>`).join('')}</select></label>`:`<label>${l}<input data-k="${k}" type="number" step="any" value="${vals?vals[k]??d:d}"></label>`).join('');}
function readForm(el){const o={};document.querySelectorAll('#'+el+' [data-k]').forEach(i=>{o[i.dataset.k]=isNaN(+i.value)||i.tagName==='SELECT'?i.value:+i.value;});return o;}
document.addEventListener('DOMContentLoaded',()=>{
 buildForm('predForm');buildForm('simForm',{distance:12,hour:20,traffic:'Low',weather:'Sunny'});
 document.getElementById('predBtn').onclick=async()=>{try{const j=await api('/api/predict-delay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(readForm('predForm'))});
  document.getElementById('predOut').innerHTML=`<div class="risk ${j.risk}">${j.risk} · ${j.probability}%</div><p>Expected delivery time: <b>${j.expected_time} min</b></p><h4>Why?</h4>${j.why.map(w=>`<div>${w.feature} ${w.pct}%<div class="bar"><i style="width:${w.pct}%"></i></div></div>`).join('')}<p class="hint">${j.note}</p>`;}catch(e){toast(e.message)}};
 document.getElementById('simBtn').onclick=async()=>{try{const j=await api('/api/what-if',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current:readForm('predForm'),simulated:readForm('simForm')})});
  document.getElementById('simOut').innerHTML=`<div class="kv"><b>Current</b><span>${j.current.time} min · ${j.current.prob}%</span><b>Simulated</b><span>${j.simulated.time} min · ${j.simulated.prob}%</span><b>Improvement</b><span>${j.improvement.minutes} min · ${j.improvement.pp} pp</span></div>`;}catch(e){toast(e.message)}};
 document.getElementById('whyBtn').onclick=explain;document.getElementById('whyRand').onclick=async()=>{try{const j=await api('/api/anomalies?limit=5');if(j.anomalies.length){document.getElementById('whySearch').value=j.anomalies[0].order_id;explain();}}catch(e){}};
});
async function explain(){
 const id=document.getElementById('whySearch').value.trim();if(!id){toast('Enter order id');return;}
 try{const j=await api('/api/orders/'+encodeURIComponent(id)+'/explanation');
  const d=j.details||{};
  document.getElementById('whyOut').innerHTML=`<div class="kpis"><div class="kpi"><div class="l">Order</div><div class="v" style="font-size:15px">${j.order_id}</div></div><div class="kpi"><div class="l">Delivery time</div><div class="v">${j.delivery_time} min</div><div class="d">${j.delayed?'<span class="bad">DELAYED</span>':'<span class="good">ON TIME</span>'} (thr ${j.threshold})</div></div><div class="kpi"><div class="l">Model delay prob</div><div class="v">${j.model_delay_probability??'—'}${j.model_delay_probability!=null?'%':''}</div></div></div>
  <div class="card"><div class="card-h">Why was this delivery late?</div><p class="hint">${j.label}</p>${(j.factors||[]).map(f=>`<div>${f.feature} — ${f.pct}%<div class="bar"><i style="width:${f.pct}%"></i></div></div>`).join('')}</div>
  <div class="card"><div class="card-h">Order snapshot</div><div class="kv">${[' _city','_traffic','_weather','_vehicle','_dist','_dtime','_rating','_hour','_order_type'].map(k=>`<b>${k}</b><span>${d[k]??'—'}</span>`).join('')}</div></div>
  <div class="card rec"><div class="card-h">Recommended Action</div><p>${j.recommended_action}</p></div>`;
 }catch(e){toast('Explain: '+e.message)}
}
