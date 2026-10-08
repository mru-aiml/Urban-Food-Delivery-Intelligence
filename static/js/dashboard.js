/* dashboard.js — overview */
async function loadDash(){
 try{
  const j=await api('/api/overview');const k=j.kpis;
  const card=(l,v,d,c)=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v??'—'}</div><div class="d ${c||''}">${d||''}</div></div>`;
  document.getElementById('kpis').innerHTML=
   card('Total Orders',k.total_orders?.toLocaleString())+card('Avg Delivery Time',k.avg_delivery_time+' min')+
   card('Avg Distance',k.avg_distance+' km')+card('Avg Rating',k.avg_rating)+
   card('On-Time %',(k.on_time_pct+'%'),'',k.on_time_pct>70?'good':'warn')+card('Delayed Orders',k.delayed_orders?.toLocaleString(),(k.delay_pct+'% delayed'),'bad')+
   card('Avg Speed',k.avg_speed+' km/h')+card('Median Time',k.median_delivery_time+' min');
  line('chOrders',j.charts.orders_over_time);bar('chHour',j.charts.time_by_hour,'#7c3aed');
  bar('chDist',j.charts.time_distribution,'#0ea5e9');bar('chWeather',j.charts.by_weather,'#10b981');
  bar('chTraffic',j.charts.by_traffic,'#f59e0b');bar('chVehicle',j.charts.by_vehicle,'#6366f1');
  bar('chCity',j.charts.by_city,'#ec4899');bar('chDelay',j.charts.delay_by_traffic||[],'#dc2626');
  document.getElementById('insights').innerHTML=j.insights.map(i=>`<div class="ins"><span class="sev">${i.severity}</span><b>${i.title}</b>${i.text}</div>`).join('')||'<div class="empty">No insights.</div>';
 }catch(e){toast('Overview: '+e.message)}
}
