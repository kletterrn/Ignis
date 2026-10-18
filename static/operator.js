'use strict';
let operatorState={},lastUpload=null,drawing=false,drawPoints=[];
let sensorResult=null;
async function op(path,body){const response=await fetch('/api/operator/'+path,{method:'POST',headers:{'X-Ignis-CSRF':config.csrf,...(body instanceof FormData?{}:{'Content-Type':'application/json'})},body:body instanceof FormData?body:JSON.stringify(body||{})});const value=await response.json();if(!response.ok)throw new Error(value.error||'Aktion fehlgeschlagen');return value;}
async function action(fn){try{$('operator-status').textContent='Wird verarbeitet …';const result=await fn();$('operator-status').textContent='Aktion abgeschlossen. '+(result?.status||'');await refreshOperator();return result;}catch(error){$('operator-status').textContent=error.message;}}
function values(form){return Object.fromEntries(new FormData(form));}
const asUTC=value=>new Date(value+'Z').toISOString();
function formHandler(id,fn){$(id).onsubmit=event=>{event.preventDefault();action(()=>fn(event.target));};}
function button(text,fn){const b=element('button','',text);b.type='button';b.onclick=()=>action(fn);return b;}
function fillBoundary(p){$('boundary-geometry').value=JSON.stringify(p.geometry,null,2);$('boundary-coverage').value=JSON.stringify(p.coverage,null,2);$('boundary-method').value=p.method||'import';$('boundary-provenance').value=p.provenance||'';if(p.acquired_at)$('boundary-time').value=p.acquired_at.slice(0,16);if(p.incident_id)$('boundary-incident').value=p.incident_id;const input=$('boundary-form').elements.resolution_m;input.value=p.resolution_m||'';}
async function refreshOperator(){
  operatorState=await apiGet('/api/operator/state');
  const jobs=$('camera-jobs');jobs.replaceChildren();for(const j of operatorState.jobs){const row=element('div','review-item');row.append(element('p','',`${j.kind}: ${j.status} · ${j.frames} Bilder · ${j.throughput_fps?.toFixed(2)||'–'} Bilder/s · ${j.device||'–'}`));if(j.error)row.append(element('p','',j.error));if(['interrupted','stopped','failed'].includes(j.status))row.append(button('Fortsetzen',()=>op('camera/resume',{id:j.id})));jobs.append(row);}
  for(const j of operatorState.jobs.filter(j=>j.frames>0)){const image=document.createElement('img');image.src='/api/operator/assets/job/'+j.id+'?v='+j.frames;image.alt='Letztes verarbeitetes Kamerabild';image.style.maxWidth='200px';jobs.append(image,button('Dieses Bild zur Prüfung markieren',()=>op('camera/snapshot',{id:j.id})));}
  const evidence=$('evidence-list');const checked=new Set([...evidence.querySelectorAll('input:checked')].map(x=>x.value));evidence.replaceChildren();for(const e of operatorState.evidence){const row=element('label','evidence-item');const input=document.createElement('input');input.type='checkbox';input.value=e.id;input.checked=checked.has(e.id);const image=document.createElement('img');image.src='/api/operator/assets/evidence/'+e.id;image.alt='Kamerabeleg zur manuellen Prüfung';row.append(input,image,element('span','',`Score ${e.model_score.toFixed(3)} · Sekunde ${e.offset_seconds} · keine Georeferenzierung`));evidence.append(row);}
  const list=$('operator-incidents');list.replaceChildren();const choice=$('boundary-incident').value;$('boundary-incident').replaceChildren();for(const i of operatorState.incidents){const option=document.createElement('option');option.value=i.id;option.textContent=i.title;$('boundary-incident').append(option);const row=element('div','review-item');row.append(element('strong','',i.title),element('p','',i.review_state),button('Veröffentlichen (ausgewählte Belege freigeben)',()=>op(`incidents/${i.id}/publish`)),button('Zurückziehen',()=>op(`incidents/${i.id}/withdraw`)));list.append(row);}if(operatorState.incidents.some(x=>x.id===choice))$('boundary-incident').value=choice;
  const review=$('perimeter-review');review.replaceChildren();for(const id of ['compare-before','compare-after']){const select=$(id),old=select.value;select.replaceChildren();for(const p of operatorState.perimeters){const o=document.createElement('option');o.value=p.id;o.textContent=`${p.acquired_at} · ${number.format(p.burned_area_ha)} ha · ${p.review_state}`;select.append(o);}select.value=old||select.options[0]?.value||'';}
  for(const p of operatorState.perimeters){const row=element('div','review-item');row.append(element('p','',`${dateText(p.acquired_at)} · ${number.format(p.burned_area_ha)} ha · ${p.review_state}`),button('Als neue Version bearbeiten',async()=>fillBoundary(p)));if(p.review_state!=='approved')row.append(button('Fläche geprüft: freigeben',()=>op(`perimeters/${p.id}/approve`)));review.append(row);}
  if(operatorState.outbox.length)$('operator-status').textContent=`${operatorState.outbox.length} Veröffentlichungen ausstehend. ${operatorState.outbox[0].error||''}`;
  const history=$('sensor-history');history.replaceChildren();for(const m of operatorState.measurements||[])history.append(button(`${m.kind} · ${dateText(m.acquired_at)}`,async()=>showSensor(await apiGet('/api/operator/measurements/'+m.id))));
}
function sensorMap(){
  if(!map||!map.isStyleLoaded()||!sensorResult?.candidate_geometry)return;
  const data=fc([feature(sensorResult.candidate_geometry)]);
  if(map.getSource('sensor-thermal'))map.getSource('sensor-thermal').setData(data);
  else{map.addSource('sensor-thermal',{type:'geojson',data});map.addLayer({id:'sensor-thermal-line',type:'line',source:'sensor-thermal',paint:{'line-color':'#f13d17','line-width':3,'line-dasharray':[2,2]}});}
}
function drawStereo(){
  if(!sensorResult?.points_preview)return;
  const canvas=$('stereo-cloud'),ctx=canvas.getContext('2d'),points=sensorResult.points_preview;
  ctx.fillStyle='#14241f';ctx.fillRect(0,0,canvas.width,canvas.height);
  const center=[0,1,2].map(i=>points.reduce((sum,p)=>sum+p[i],0)/points.length);
  const radius=Math.max(...points.map(p=>Math.hypot(p[0]-center[0],p[1]-center[1],p[2]-center[2])),.001);
  const angle=Number($('stereo-yaw').value)*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle);
  const projected=points.map(p=>{const x=p[0]-center[0],y=p[1]-center[1],z=p[2]-center[2];return {x:(c*x+s*z)/radius,y:y/radius,z:(-s*x+c*z)/radius,color:`rgb(${p[3]},${p[4]},${p[5]})`};}).sort((a,b)=>b.z-a.z);
  for(const p of projected){const scale=300/(2+p.z);ctx.fillStyle=p.color;ctx.fillRect(canvas.width/2+p.x*scale,canvas.height/2+p.y*scale,2,2);}
  ctx.fillStyle='white';ctx.fillText(`Lokale Kamerakoordinaten · Ausdehnung der Vorschau ±${number.format(radius)} m · keine Georeferenzierung`,12,22);
}
function showSensor(result){
  sensorResult=result;
  const {points_preview,candidate_geometry,coverage,...summary}=result;
  $('sensor-report').textContent=JSON.stringify(summary,null,2);
  $('sensor-preview').src=`/api/operator/measurements/${result.id}/preview`;$('sensor-preview').hidden=false;
  $('stereo-view').hidden=result.kind!=='stereo';
  const links=$('sensor-downloads');links.replaceChildren();
  for(const [artifact,label] of [['report','Messbericht (JSON)'],...(result.kind==='stereo'?[['points','Punktwolke (PLY)'],['depth','Tiefe + Gültigkeit (NPZ)']]:[['candidate','Wärmekandidat (GeoJSON)']])]){const link=document.createElement('a');link.href=`/api/operator/measurements/${result.id}/${artifact}`;link.textContent=label;links.append(link);}
  if(map?.getSource('sensor-thermal'))map.getSource('sensor-thermal').setData(fc([]));
  sensorMap();drawStereo();
  if(map&&candidate_geometry){const polygons=candidate_geometry.type==='Polygon'?[candidate_geometry.coordinates]:candidate_geometry.coordinates;const bounds=new maplibregl.LngLatBounds();for(const rings of polygons)for(const point of rings[0])bounds.extend(point);map.fitBounds(bounds,{padding:70,maxZoom:17});}
  return result;
}
$('stereo-yaw').oninput=drawStereo;
if(map){map.on('styledata',sensorMap);map.on('idle',()=>{if(!map.getSource('sensor-thermal'))sensorMap();});}
formHandler('stereo-form',async form=>{const body=new FormData(form);for(const key of ['left_at','right_at'])body.set(key,asUTC(body.get(key)));return showSensor(await op('sensors/stereo',body));});
formHandler('thermal-form',async form=>showSensor(await op('sensors/thermal',new FormData(form))));
formHandler('upload-form',async form=>{const r=await op('upload',new FormData(form));lastUpload=r;$('camera-upload').value=r.id;$('upload-result').textContent=`Upload-ID: ${r.id} · ${r.count} Datei(en)`;if(r.geometry)$('boundary-geometry').value=JSON.stringify(r.geometry,null,2);if(r.raster){$('boundary-coverage').value=JSON.stringify(r.raster.coverage,null,2);$('raster-preview').src='/api/operator/assets/raster/'+r.id;$('raster-preview').hidden=false;if(map&&map.isStyleLoaded()){const [w,s,e,n]=r.raster.bounds;if(map.getLayer('operator-raster-layer'))map.removeLayer('operator-raster-layer');if(map.getSource('operator-raster'))map.removeSource('operator-raster');map.addSource('operator-raster',{type:'image',url:$('raster-preview').src,coordinates:[[w,n],[e,n],[e,s],[w,s]]});map.addLayer({id:'operator-raster-layer',type:'raster',source:'operator-raster',paint:{'raster-opacity':.8}},map.getLayer('reviewed-fill')?'reviewed-fill':undefined);map.fitBounds([[w,s],[e,n]],{padding:60});}}return r;});
formHandler('camera-form',form=>{const d=values(form);if(d.acquired_at)d.acquired_at=asUTC(d.acquired_at);return op('camera/start',d);});
$('camera-stop').onclick=()=>action(()=>op('camera/stop'));
$('collect-local').onclick=()=>action(()=>op('collect'));
$('sync-cloud').onclick=()=>action(()=>op('sync'));
formHandler('incident-form',form=>op('incidents',{...values(form),evidence_ids:[...$('evidence-list').querySelectorAll('input:checked')].map(x=>x.value)}));
formHandler('boundary-form',form=>{const d=values(form);d.geometry=JSON.parse(d.geometry);d.coverage=JSON.parse(d.coverage);d.acquired_at=asUTC(d.acquired_at);d.resolution_m=d.resolution_m?Number(d.resolution_m):null;return op('perimeters',d);});
formHandler('compare-form',async form=>{const r=await op('compare',values(form));$('compare-result').textContent=JSON.stringify(r,null,2);return r;});
formHandler('scene-form',async form=>{const d=values(form);d.bbox=d.bbox.split(',').map(Number);d.start=asUTC(d.start);d.end=asUTC(d.end);const r=await op('imagery/search',d);$('scene-list').replaceChildren();for(const s of r.scenes){const row=element('div','review-item');row.append(element('p','',`${s.id} · ${dateText(s.acquired_at)} · Wolken ${s.cloud_cover??'?'} %`));for(const slot of ['before','after'])row.append(button(slot==='before'?'Als Vorher laden':'Als Nachher laden',async()=>{const image=await op('imagery/download',{bbox:d.bbox,acquired_at:s.acquired_at});$('outline-'+slot).value=image.id;return image;}));$('scene-list').append(row);}return r;});
formHandler('outline-form',async form=>{const r=await op('imagery/outline',values(form));fillBoundary(r);return r;});
$('draw-start').onclick=()=>{drawing=true;drawPoints=[];$('operator-status').textContent='Eckpunkte auf der Karte anklicken. Mit „Zeichnen beenden“ schließen.';if(map)map.getCanvas().style.cursor='crosshair';};
$('draw-finish').onclick=()=>{drawing=false;if(map)map.getCanvas().style.cursor='';if(drawPoints.length>=3){$('boundary-geometry').value=JSON.stringify({type:'Polygon',coordinates:[[...drawPoints,drawPoints[0]]]},null,2);$('operator-status').textContent='Polygon übernommen. Abdeckung aus der tatsächlichen Aufnahme ergänzen.';}};
if(map)map.on('click',event=>{if(!drawing)return;drawPoints.push([Number(event.lngLat.lng.toFixed(7)),Number(event.lngLat.lat.toFixed(7))]);const data=fc(drawPoints.map(c=>feature({type:'Point',coordinates:c})));if(map.getSource('draw-points'))map.getSource('draw-points').setData(data);else{map.addSource('draw-points',{type:'geojson',data});map.addLayer({id:'draw-points-layer',type:'circle',source:'draw-points',paint:{'circle-color':'#558ed8','circle-radius':5}});}});
refreshOperator();setInterval(()=>refreshOperator().catch(()=>{}),5000);
