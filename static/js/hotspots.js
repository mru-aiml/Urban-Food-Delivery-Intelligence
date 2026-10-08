/* hotspots.js + recs */
let map=null;
async function loadHot(){
 try{const j=await api('/api/hotspots');
  document.getElementById('geoNote').textContent=j.has_geo?'Green <35% · Yellow 35-60% · Red >60% delay. Grid-aggregated real coordinates.':'No valid lat/lon in dataset — showing city/area hotspot table instead.';
  if(j.has_geo&&window.L){
   if(map)map.remove();
   map=L.map('map').setView([j.points[0].lat,j.points[0].lon],5);
   L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OSM'}).addTo(map);
   j.points.forEach(p=>{L.circleMarker([p.lat,p.lon],{radius:6+Math.min(10,p.orders/20),color:p.color==='green'?'#16a34a':p.color==='yellow'?'#d97706':'#dc2626',fillOpacity:.6}).bindPopup(`Orders ${p.orders}<br>Avg ${p.avg_time} min<br>Delay ${p.delay_rate}%`).addTo(map);});
  } else document.getElementById('map').innerHTML='<div class="empty">Geographic coordinates unavailable — see table below.</div>';
  document.querySelector('#hotTable tbody').innerHTML=(j.areas||[]).map(a=>`<tr><td>${a.label}</td><td>${a.orders}</td><td>${a.avg_time}</td><td>${a.delay_rate}%</td><td>${a.avg_distance}</td><td>${a.avg_rating}</td></tr>`).join('');
 }catch(e){toast(e.message)}
}
async function loadRecs(){
 try{const j=await api('/api/recommendations');
  document.getElementById('recList').innerHTML=j.recommendations.map(r=>`<div class="card rec"><div class="card-h"><i class="fa fa-wand-magic-sparkles"></i> ${r.problem}</div><div class="kv"><b>PROBLEM</b><span>${r.problem}</span><b>EVIDENCE</b><span>${r.evidence}</span><b>ACTION</b><span>${r.action}</span><b>EXPECTED IMPACT</b><span>${r.expected_impact}</span></div></div>`).join('');
 }catch(e){toast(e.message)}
}
