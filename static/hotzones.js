/* Approximate sensor sampling context, never a fire perimeter or area measurement. */
(function(root) {
  'use strict';
  function confidence(value) {
    const raw=String(value).trim().toLowerCase();
    if(raw==='h'||raw==='high'||(raw!==''&&Number(raw)>=80))return 'high';
    if(raw==='n'||raw==='nominal'||(raw!==''&&Number(raw)>=30))return 'nominal';
    return 'low';
  }
  function industrial(o){return o.context_kind==='industrial'||o.context_kind==='static_source';}
  function buildHotZones(observations) {
    const seen=new Set(),features=[];
    for(const o of observations){
      if(industrial(o)||!Number.isFinite(o.latitude)||!Number.isFinite(o.longitude)||Math.abs(o.latitude)>89||Math.abs(o.longitude)>180)continue;
      const identity=JSON.stringify([o.satellite,o.sensor,o.detected_at,o.latitude,o.longitude]);
      if(seen.has(identity))continue;seen.add(identity);
      const dimensions=[o.scan_km,o.track_km];
      const supplied=dimensions.every(v=>Number.isFinite(v)&&v>0&&v<=10);
      // Scan orientation is unavailable; a circumcircle avoids inventing a rotated pixel boundary.
      const radius=supplied?Math.hypot(...dimensions)*500:(String(o.sensor).toUpperCase().includes('VIIRS')?375:1000);
      const ring=[],lat=o.latitude*Math.PI/180,lon=o.longitude*Math.PI/180,d=radius/6371000;
      for(let i=0;i<32;i++){
        const bearing=i*2*Math.PI/32;
        const y=Math.asin(Math.sin(lat)*Math.cos(d)+Math.cos(lat)*Math.sin(d)*Math.cos(bearing));
        const x=lon+Math.atan2(Math.sin(bearing)*Math.sin(d)*Math.cos(lat),Math.cos(d)-Math.sin(lat)*Math.sin(y));
        ring.push([((x*180/Math.PI+540)%360)-180,y*180/Math.PI]);
      }
      if(Math.max(...ring.map(p=>p[0]))-Math.min(...ring.map(p=>p[0]))>180)continue;
      ring.push([...ring[0]]);
      features.push({type:'Feature',geometry:{type:'Polygon',coordinates:[ring]},properties:{count:1,satellites:o.satellite,latest:o.detected_at,radius_m:Math.round(radius),method:supplied?'FIRMS scan/track circumcircle':'nominal sensor context',measurement:false}});
    }
    return {type:'FeatureCollection',features};
  }
  const api={confidence,industrial,buildHotZones};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.IgnisZones=api;
})(typeof window!=='undefined'?window:globalThis);
