/* Hot zones are observation-density cells, not fire perimeters or risk predictions. */
(function(root) {
  'use strict';
  function confidence(value) {
    const raw = String(value).trim().toLowerCase();
    if (raw === 'h' || raw === 'high' || (raw !== '' && Number(raw) >= 80)) return 'high';
    if (raw === 'n' || raw === 'nominal' || (raw !== '' && Number(raw) >= 30)) return 'nominal';
    return 'low';
  }
  function buildHotZones(observations) {
    const cells = new Map(), seen = new Set(), size = 0.05;
    for (const o of observations) {
      if (confidence(o.confidence) === 'low' || !Number.isFinite(o.latitude) || !Number.isFinite(o.longitude) || Math.abs(o.latitude)>90 || Math.abs(o.longitude)>180) continue;
      const identity = JSON.stringify([o.satellite,o.sensor,o.detected_at,o.latitude,o.longitude]);
      if (seen.has(identity)) continue;
      seen.add(identity);
      const x=Math.min(7199,Math.floor((o.longitude+180)/size));
      const y=Math.min(3599,Math.floor((o.latitude+90)/size));
      const key=`${x}:${y}`;
      if (!cells.has(key)) cells.set(key,{x,y,count:0,high:0,satellites:new Set(),latest:''});
      const cell=cells.get(key);
      cell.count++; cell.high+=Number(confidence(o.confidence)==='high');
      cell.satellites.add(o.satellite);
      if (o.detected_at>cell.latest) cell.latest=o.detected_at;
    }
    return {type:'FeatureCollection',features:[...cells.values()].filter(cell=>cell.count>=3).map(cell=>{
      const west=Number((cell.x*size-180).toFixed(5)),south=Number((cell.y*size-90).toFixed(5));
      const east=Number((west+size).toFixed(5)),north=Number((south+size).toFixed(5));
      return {type:'Feature',geometry:{type:'Polygon',coordinates:[[[west,south],[east,south],[east,north],[west,north],[west,south]]]},properties:{count:cell.count,high:cell.high,satellites:[...cell.satellites].sort().join(', '),latest:cell.latest}};
    })};
  }
  const api={confidence,buildHotZones};
  if (typeof module !== 'undefined' && module.exports) module.exports=api;
  else root.IgnisZones=api;
})(typeof window !== 'undefined'?window:globalThis);
