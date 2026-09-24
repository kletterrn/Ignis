'use strict';
const config = JSON.parse(document.getElementById('app-config').textContent);
const $ = (id) => document.getElementById(id);
let observations = [], visible = [], hours = 24, feedStatus = 'loading', feedMessage = '', map, popup, requestId = 0;
const number = new Intl.NumberFormat('de-DE', {maximumFractionDigits: 1});
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const {confidence, buildHotZones} = window.IgnisZones;
const {composeStyle, germanStyle, imageryStyle, createStyleSwitcher} = window.IgnisMaps;
const {assessObservations} = window.IgnisVerification;
const basemapCache = new Map();
let activeBasemap = 'streets';
let hotZones = buildHotZones([]);
const selectedSources = new Set([config.source in config.sources ? config.source : Object.keys(config.sources)[0]]);
function collection() {
  return {type:'FeatureCollection',features:visible.map(o => ({type:'Feature',geometry:{type:'Point',coordinates:[o.longitude,o.latitude]},properties:{...o,level:confidence(o.confidence)}}))};
}
function resetView() {
  if (!map) return;
  if (config.view.bounds) map.fitBounds(config.view.bounds, {padding:45,duration:reducedMotion?0:700});
  else map.flyTo({...config.view,duration:reducedMotion?0:700});
}
function mapNotice(message) { $('map-error').textContent = message; $('map-error').hidden = false; }
function cartoStyle(name) {
  return `https://basemaps.cartocdn.com/gl/${name === 'dark' ? 'dark-matter' : 'voyager'}-gl-style/style.json`;
}
// Authenticate CARTO resources only; never forward this key to other providers.
function cartoRequest(url) {
  const resource = new URL(url, window.location.href);
  if (resource.protocol === 'https:' && (resource.hostname === 'basemaps.cartocdn.com' || resource.hostname.endsWith('.basemaps.cartocdn.com'))) {
    resource.searchParams.set('key', config.cartoKey);
    return {url:resource.href};
  }
  return {url};
}
async function loadBasemap(name) {
  if(name==='imagery') return imageryStyle();
  if(!config.cartoKey || config.cartoKey==='PASTE_YOUR_CARTO_BASEMAP_KEY_HERE') throw new Error('Für die Standardkarte fehlt der CARTO-Schlüssel in .env. Wähle alternativ Satellitenbild.');
  if(basemapCache.has(name))return basemapCache.get(name);
  const response=await fetch(cartoRequest(cartoStyle(name)).url,{signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw new Error('Die Karte konnte nicht geladen werden. Prüfe den CARTO-Schlüssel oder wähle Satellitenbild.');
  const style=germanStyle(await response.json());
  basemapCache.set(name,style);return style;
}
const switchBasemap=createStyleSwitcher(loadBasemap,(base,name)=>{
  // Data is read at apply time, so source/filter changes during loading are preserved.
  map.setStyle(composeStyle(base,collection(),hotZones,$('show-hotspots').checked,$('show-zones').checked));
  activeBasemap=name;
  $('map-error').hidden=true;
  $('basemap-note').textContent=name==='imagery'?'Esri-Satellitenbild · Aufnahmedatum unterschiedlich · kein Livebild':'Karte von CARTO / OpenStreetMap';
});
async function changeBasemap(name) {
  if(!map)return;
  $('basemap-note').textContent='Karte wird geladen …';
  try {await switchBasemap(name);}
  catch(error){
    if(name!=='imagery' && activeBasemap==='streets' && !basemapCache.has('streets')) {
      try { await switchBasemap('imagery'); $('basemap').value='imagery'; mapNotice('Die Standardkarte ist nicht verfügbar. Stattdessen wird das Satellitenbild angezeigt.'); return; } catch {}
    }
    $('basemap').value=activeBasemap;mapNotice(error.message);$('basemap-note').textContent='Kartenwechsel fehlgeschlagen. Die bisherigen Daten bleiben erhalten.';
  }
}
function initMap() {
  if (!window.maplibregl) { mapNotice('Die Karte konnte nicht geladen werden. Prüfe deine Internetverbindung. Die Wärmehinweise bleiben in der Liste sichtbar.'); return; }
  try {
    const empty={version:8,glyphs:'https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf',sources:{},layers:[{id:'background',type:'background',paint:{'background-color':'#14241f'}}]};
    map = new maplibregl.Map({container:'map',style:composeStyle(empty,collection(),hotZones,true,true),transformRequest:cartoRequest,center:config.view.center||[10.45,51.15],zoom:config.view.zoom||5,attributionControl:true});
    const fireCanvas=document.createElement('canvas');fireCanvas.width=64;fireCanvas.height=64;
    const fireContext=fireCanvas.getContext('2d');fireContext.font='52px "Segoe UI Emoji", "Apple Color Emoji", sans-serif';fireContext.textAlign='center';fireContext.textBaseline='middle';fireContext.fillText('\u{1F525}',32,34);
    map.on('styleimagemissing',event=>{if(event.id==='fire-emoji'&&!map.hasImage(event.id))map.addImage(event.id,fireContext.getImageData(0,0,64,64));});
    map.addControl(new maplibregl.NavigationControl({showCompass:false}), 'top-right');
    map.addControl(new maplibregl.ScaleControl({unit:'metric'}),'bottom-right');
    resetView();
    map.on('error', () => mapNotice('Karteninhalte konnten nicht geladen werden. Prüfe deine Verbindung oder wähle eine andere Kartenansicht.'));
    // No style.load dependency: style diffing can remove overlays without firing it.
    map.once('load',()=>changeBasemap($('basemap').value));
      map.on('click','zone-fill',event=>{
        const pointLayers=['hotspots','high-fire','clusters'].filter(id=>map.getLayer(id));
        if(pointLayers.length && map.queryRenderedFeatures(event.point,{layers:pointLayers}).length) return;
        const zone=event.features[0].properties, content=element('div','popup-content');
        content.append(element('div','popup-title','Bereich mit mehreren Wärmehinweisen'));
        content.append(element('div','',`${zone.count} Wärmehinweise (mittel/hoch) · ${hours} Std.`));
        content.append(element('div','',`Satelliten: ${zone.satellites}`));
        content.append(element('div','',`Neuester Hinweis: ${zone.latest}`));
        content.append(element('div','', 'Rasterzelle (0,05°) – keine bestätigte Brandfläche.'));
        popup?.remove();popup=new maplibregl.Popup({maxWidth:'320px'}).setLngLat(event.lngLat).setDOMContent(content).addTo(map);
      });
      for(const layer of ['hotspots','high-fire']) map.on('click',layer,event => selectObservation(event.features[0].properties));
      map.on('click','clusters',async event => {
        try { const f=event.features[0]; const zoom=await map.getSource('detections').getClusterExpansionZoom(f.properties.cluster_id); map.easeTo({center:f.geometry.coordinates,zoom,duration:reducedMotion?0:500}); } catch { mapNotice('Die Gruppe konnte nicht geöffnet werden. Bitte näher heranzoomen.'); }
      });
      for (const layer of ['clusters','hotspots','high-fire','zone-fill']) {
        map.on('mouseenter',layer,()=>map.getCanvas().style.cursor='pointer');
        map.on('mouseleave',layer,()=>map.getCanvas().style.cursor='');
      }
  } catch { mapNotice('Dein Browser unterstützt die Karte möglicherweise nicht. Die Wärmehinweise können weiterhin angesehen und exportiert werden.'); }
}
function setZones() {
  for(const layer of ['zone-fill','zone-outline']) if(map?.getLayer(layer)) map.setLayoutProperty(layer,'visibility',$('show-zones').checked?'visible':'none');
  popup?.remove();
}
function setHotspots() {
  for (const layer of ['clusters','cluster-count','hotspot-glow','hotspots','high-fire']) if (map?.getLayer(layer)) map.setLayoutProperty(layer,'visibility',$('show-hotspots').checked?'visible':'none');
  if (!$('show-hotspots').checked) popup?.remove();
}
function confidenceLabel(level) { return level==='high'?'Hoch':level==='nominal'?'Mittel':'Niedrig / unbekannt'; }
function verificationLabel(value) { return value==='Cross-satellite support'?'Mehrere Satelliten':'Nicht bestätigt'; }
function translateStatus(status, message) { return ({connected:'Satellitendaten erfolgreich geladen.',partial:'Einige Satelliten sind nicht erreichbar.',configuration_missing:'Trage deinen NASA-FIRMS-Schlüssel in .env ein und starte die App neu.',unavailable:'NASA FIRMS ist momentan nicht erreichbar. Prüfe die Einstellungen.'})[status]||message; }
function element(tag, className, text) { const node=document.createElement(tag); node.className=className; if (text !== undefined) node.textContent=text; return node; }
function selectObservation(o) {
  if (!map) return;
  const coordinates=[Number(o.longitude),Number(o.latitude)];
  map.flyTo({center:coordinates,zoom:Math.max(map.getZoom(),10),duration:reducedMotion?0:900});
  popup?.remove();
  const content=element('div','popup-content');
  content.append(element('div','popup-title','Wärmehinweis'));
  for (const [label,value] of [['Ort',`${coordinates[1].toFixed(3)}, ${coordinates[0].toFixed(3)}`],['Datenquelle',o.dataset||o.source],['Satellit',o.satellite],['Sensor',o.sensor],['Erkannt',o.detected_at],['Einstufung',confidenceLabel(confidence(o.confidence))],['Wärmeleistung',`${o.frp} MW`],['Tag / Nacht',o.daynight==='D'?'Tag':o.daynight==='N'?'Nacht':o.daynight]]) {
    const row=element('div','popup-row');row.append(element('span','',label),element('b','',String(value)));content.append(row);
  }
  const evidence=element('div','verification-evidence');
  evidence.append(element('strong','',verificationLabel(o.verification)),element('p','',o.verification_detail||'Kein zusätzlicher Abgleich verfügbar.'),element('p','','Kein bestätigter Waldbrand. Prüfe offizielle Meldungen. Das Satellitenbild ist kein Livebild.'));
  content.append(evidence);
  popup=new maplibregl.Popup({offset:12,maxWidth:'320px'}).setLngLat(coordinates).setDOMContent(content).addTo(map);
}
function render() {
  popup?.remove();
  const query=$('search').value.trim().toLowerCase(), level=$('confidence').value;
  visible=observations.filter(o=>(level==='all'||confidence(o.confidence)===level)&&`${o.satellite} ${o.sensor} ${o.latitude} ${o.longitude}`.toLowerCase().includes(query));
  const connected=feedStatus==='connected'||feedStatus==='partial';
  hotZones=buildHotZones(visible);
  const supported=visible.filter(o=>o.verification==='Cross-satellite support').length;
  $('verification-summary').textContent=connected?`${supported} Hinweise mit Übereinstimmung mehrerer Satelliten · ${visible.length-supported} ohne solchen Abgleich. Keine unabhängige Brandbestätigung · ${hours} Std.${feedStatus==='partial'?' · einige Quellen nicht verfügbar':''}.`:'Abgleich verfügbar, sobald Satellitendaten geladen sind.';
  $('zone-count').textContent=connected?`${hotZones.features.length} verdichtete Bereiche`:'Keine Bereichsdaten verfügbar';
  map?.getSource('hot-zones')?.setData(hotZones);
  $('total').textContent=connected?number.format(visible.length):'—';
  $('high').textContent=connected?number.format(visible.filter(o=>confidence(o.confidence)==='high').length):'—';
  $('power').textContent=connected?number.format(visible.reduce((sum,o)=>sum+o.frp,0)):'—';
  $('window-caption').textContent=`Letzte ${hours} ${hours===1?'Stunde':'Stunden'} · gefiltert`;
  $('list-count').textContent=visible.length;
  $('mapped-count').textContent=`${number.format(visible.length)} Hinweise · ${hours} Std.`;
  $('export').disabled=!visible.length;
  $('list-summary').textContent=visible.length>200?`200 von ${visible.length} Hinweisen`:`${visible.length} Hinweise`;
  const list=$('detection-list');list.replaceChildren();
  if (!visible.length) {
    const empty=element('div','empty-state');
    const title=feedStatus==='loading'?'Verbindung wird hergestellt':feedStatus==='configuration_missing'?'Satellitendaten einrichten':feedStatus==='unavailable'?'Satellitendaten nicht verfügbar':observations.length?'Keine passenden Wärmehinweise':'Keine Hinweise in diesem Zeitraum';
    const message=connected?(observations.length?'Versuche einen anderen Suchbegriff oder Filter.':'Versuche einen längeren Zeitraum. Keine Hinweise bedeuten nicht, dass es keine Brände gibt.'):feedMessage||'Satellitendaten werden abgerufen.';
    empty.append(element('span','empty-icon','◎'),element('h3','',title),element('p','',message));list.append(empty);
  }
  for (const o of visible.slice(0,200)) {
    const button=element('button','detection');
    const top=element('div','detection-top'),bottom=element('div','detection-bottom');
    top.append(element('span','',`${o.latitude.toFixed(3)}°, ${o.longitude.toFixed(3)}°`),element('span','confidence-pill',confidenceLabel(confidence(o.confidence))));
    bottom.append(element('span','',`${o.satellite} · ${number.format(o.frp)} MW`),element('span','',o.detected_at.slice(5)));
    button.append(top,bottom,element('div','verification-badge',verificationLabel(o.verification)));button.addEventListener('click',()=>{selectObservation(o);document.querySelectorAll('.detection.selected').forEach(node=>node.classList.remove('selected'));button.classList.add('selected');});list.append(button);
  }
  map?.getSource('detections')?.setData(collection());
}
async function refresh() {
  const id=++requestId;
  for(const id of Object.keys(config.sources)) $('status-'+id).textContent=selectedSources.has(id)?'Wird aktualisiert …':'Nicht ausgewählt';
  if(!selectedSources.size){observations=[];feedStatus='configuration_missing';feedMessage='Wähle mindestens einen Satelliten aus.';$('source-message').textContent=feedMessage;$('connection-label').textContent='Kein Satellit ausgewählt';$('network-summary').textContent='0 ausgewählt';$('source-caption').textContent='Keine Datenquelle ausgewählt';$('connection-dot').className='';$('refresh').disabled=false;render();return;}
  $('refresh').disabled=true;$('connection-label').textContent='Satellitendaten werden aktualisiert …';
  try {
    const response=await fetch(`/api/observations?hours=${hours}&sources=${encodeURIComponent([...selectedSources].join(','))}`,{signal:AbortSignal.timeout(55000)});
    const data=await response.json();
    if (id!==requestId) return;
    if (!Array.isArray(data.observations)) throw new Error('Ungültige Antwort');
    observations=assessObservations(data.observations);feedStatus=data.status;feedMessage=translateStatus(data.status,data.message);
    for(const source of data.sources||[]) $('status-'+source.id).textContent=source.status==='connected'?`${source.count} Hinweise`:'Nicht verfügbar';
    if(data.status==='configuration_missing') for(const source of selectedSources) $('status-'+source).textContent='API-Schlüssel fehlt';
    $('network-summary').textContent=`${(data.sources||[]).filter(source=>source.status==='connected').length} / ${selectedSources.size} verbunden`;
    $('source-caption').textContent=`${selectedSources.size} ausgewählte Satelliten`;
    $('source-message').textContent=feedMessage=translateStatus(data.status, data.message);
    $('checked-at').textContent=`Aktualisiert: ${new Date(data.checked_at).toLocaleTimeString('de-DE',{timeZone:'Europe/Berlin',hour:'2-digit',minute:'2-digit'})} Uhr`;
  } catch {
    if(id!==requestId)return;
    observations=[];feedStatus='unavailable';feedMessage='Daten konnten nicht abgerufen werden. Prüfe die Verbindung und versuche es erneut.';
    $('checked-at').textContent='Aktualisierung fehlgeschlagen';
    $('source-message').textContent=feedMessage;
    for(const source of selectedSources) $('status-'+source).textContent='Nicht verfügbar';
    $('network-summary').textContent=`0 / ${selectedSources.size} verbunden`;
  } finally {
    if(id===requestId){$('refresh').disabled=false;$('connection-label').textContent=feedStatus==='connected'?'NASA FIRMS verbunden':feedStatus==='partial'?'Einige Satelliten nicht verfügbar':feedStatus==='configuration_missing'?'API-Schlüssel fehlt':'Satellitendaten nicht verfügbar';$('connection-dot').className=feedStatus==='connected'?'connected':'';render();}
  }
}
$('refresh').addEventListener('click',refresh);
for(const button of document.querySelectorAll('[data-hours]')) button.addEventListener('click',()=>{
  hours=Number(button.dataset.hours);observations=[];feedStatus='loading';feedMessage='Hinweise für den gewählten Zeitraum werden geladen.';render();
  for(const item of document.querySelectorAll('[data-hours]')){item.classList.toggle('selected',item===button);item.setAttribute('aria-pressed',String(item===button));}
  refresh();
});
$('confidence').addEventListener('change',render);$('search').addEventListener('input',render);
$('show-zones').addEventListener('change',setZones);
$('show-hotspots').addEventListener('change',setHotspots);$('fit-map').addEventListener('click',resetView);
$('basemap').addEventListener('change',()=>changeBasemap($('basemap').value));
$('export').addEventListener('click',()=>{
  const columns=['latitude','longitude','detected_at','satellite','sensor','confidence','frp','daynight','source','dataset','verification','verification_detail'];
  const cell=value=>'"'+String(value).replace(/^[=+@-]/,"'$&").replaceAll('"','""')+'"';
  const csv=[columns.join(','),...visible.map(o=>columns.map(key=>cell(o[key])).join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8;'}));const link=document.createElement('a');link.href=url;link.download=`ignis-observations-${hours}h.csv`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('region-caption').textContent=config.area==='5.8,47.2,15.1,55.1'?'Deutschland und Umgebung':config.area.toLowerCase()==='world'?'Weltweit':`Beobachtete Region · ${config.area}`;
for(const [id,label] of Object.entries(config.sources)) {
  const card=element('label','satellite-source');
  const input=document.createElement('input');input.type='checkbox';input.checked=selectedSources.has(id);input.value=id;input.setAttribute('aria-label',label);
  const details=element('span','satellite-details');details.append(element('strong','',label));
  const status=element('small','', 'Wartet');status.id='status-'+id;details.append(status);card.append(input,details);$('satellite-sources').append(card);
  input.addEventListener('change',()=>{if(input.checked)selectedSources.add(id);else selectedSources.delete(id);observations=[];feedStatus='loading';render();refresh();});
}
$('source-caption').textContent=`${selectedSources.size} ausgewählte ${selectedSources.size===1?'Datenquelle':'Datenquellen'}`;
function clock(){ $('clock').textContent=new Date().toLocaleDateString('de-DE',{day:'2-digit',month:'short',year:'numeric',timeZone:'Europe/Berlin'}); }
clock();initMap();refresh();setInterval(()=>{if(!document.hidden)refresh();},600000);
