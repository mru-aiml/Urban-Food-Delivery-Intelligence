/* delivery.js — filters, metrics, SLA */
let delOpts={};
async function loadDelivery(){
 try{
  const q=new URLSearchParams();['city','weather','traffic','vehicle','order_type'].forEach(k=>{const v=document.getElementById('f_'+k)?.value;if(v&&v!=='all')q.set(k,v);});
  const j=await api('/api/delivery-analytics?'+q.toString());
  delOpts=j.options;
  const f=document.getElementById('delFilters');
  if(!f.dataset.built){f.dataset.built=1;
   f.innerHTML=[['city','cities'],['weather','weather'],['traffic','traffic'],['vehicle','vehicles'],['order_type','order_types']].map(([k,ok])=>`<label>${k}<select id="f_${k}"><option value="all">All</option></select></label>`).join('')+`<button class="btn primary" onclick="loadDelivery()">Apply</button>`;
  }
  [['city','cities'],['weather','weather'],['traffic','traffic'],['vehicle','vehicles'],['order_type','order_types']].forEach(([k,ok])=>{const s=document.getElementById('f_'+k);const cur=s.value;const opts=j.options[ok]||[];s.innerHTML='<option value="all">All</option>'+opts.map(o=>`<option ${o===cur?'selected':''}>${o}</option>`).join('');});
  const m=j.metrics;
  document.getElementById('delKpis').innerHTML=['count|Orders|','avg_delivery_time|Avg Time|min|','avg_distance|Avg Dist|km|','avg_speed|Avg Speed|km/h|','delay_rate|Delay %|%|bad','on_time_rate|On-Time %|%|good','avg_rating|Rating||'].map(s=>{const[k,l,u,c]=s.split('|');return `<div class="kpi"><div class="l">${l}</div><div class="v">${m[k]??'—'}${m[k]!=null?u:''}</div></div>`;}).join('');
  const c=j.charts;
  if(c.time_vs_distance.length)mkChart('dScatter',{type:'scatter',data:{datasets:[{data:c.time_vs_distance,label:'orders',backgroundColor:'#4f46e5'}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{title:{display:true,text:'distance (km)'}},y:{title:{display:true,text:'time (min)'}}}}});
  bar('dTraffic',c.time_by_traffic,'#f59e0b');bar('dWeather',c.time_by_weather,'#10b981');bar('dVehicle',c.time_by_vehicle,'#6366f1');bar('dHour',c.time_by_hour,'#7c3aed');
  const s=j.summary;let h='<div class="kv">';
  const add=(k,v)=>{if(v)h+=`<b>${k}</b><span>${v}</span>`;};
  if(s.worst_traffic)add('Worst traffic',`${s.worst_traffic.label} (${s.worst_traffic.avg} min)`);if(s.best_traffic)add('Best traffic',`${s.best_traffic.label} (${s.best_traffic.avg} min)`);
  if(s.worst_weather)add('Worst weather',`${s.worst_weather.label} (${s.worst_weather.avg} min)`);if(s.worst_city)add('Worst city',`${s.worst_city.label} (${s.worst_city.avg} min)`);
  if(s.peak_delay_hour)add('Peak delay hour',`${s.peak_delay_hour.label} (${s.peak_delay_hour.avg} min)`);
  document.getElementById('perfSummary').innerHTML=h+'</div>';
  loadSLA();
 }catch(e){toast('Delivery: '+e.message)}
}
async function loadSLA(){
 const sla=document.getElementById('slaInput').value||40;
 try{const j=await api(`/api/orders?sla=${sla}&size=10`);
  document.getElementById('slaCards').innerHTML=Object.entries(j.sla_summary||{}).map(([k,v])=>`<div class="sla" onclick="filterSLA('${k}')"><div>${k}</div><b>${v.pct}%</b> · ${v.count}</div>`).join('');
  document.querySelector('#slaTable tbody').innerHTML=j.rows.map(r=>`<tr><td>${r._oid??''}</td><td>${r._city??''}</td><td>${r._dtime??''} min</td><td>${r._sla_band??''}</td></tr>`).join('');
 }catch(e){}
}
function filterSLA(b){sessionStorage.setItem('band',b);go('explorer');if(window.loadExplorer)loadExplorer();}
document.addEventListener('DOMContentLoaded',()=>{document.getElementById('slaBtn')?.addEventListener('click',loadSLA);});
