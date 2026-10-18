const {test}=require('node:test');
const assert=require('node:assert/strict');
const {buildHotZones}=require('../static/hotzones.js');
const {composeStyle}=require('../static/maps.js');

test('sensor context follows points and pixel dimensions, never density squares or measurements',()=>{
  const sample={latitude:50.001,longitude:10.017,satellite:'N21',sensor:'VIIRS',confidence:'n',detected_at:'2026-10-18T12:00:00Z',scan_km:.4,track_km:.6};
  const result=buildHotZones([sample,sample,{...sample,longitude:10.1,context_kind:'industrial'},{...sample,latitude:NaN}]);
  assert.equal(result.features.length,1);
  const feature=result.features[0],ring=feature.geometry.coordinates[0];
  assert.equal(ring.length,33);assert.deepEqual(ring[0],ring.at(-1));
  assert.equal(feature.properties.radius_m,361);assert.equal(feature.properties.measurement,false);
  assert.ok(Math.max(...ring.map(p=>p[0]))-Math.min(...ring.map(p=>p[0]))<.012);
  assert.ok(Math.abs((Math.max(...ring.map(p=>p[0]))+Math.min(...ring.map(p=>p[0])))/2-sample.longitude)<.00001);
});

test('industrial context is gray and cannot receive a fire icon even at high confidence',()=>{
  const empty={type:'FeatureCollection',features:[]},style=composeStyle({version:8,sources:{},layers:[]},empty,empty,true,true);
  const points=style.layers.find(l=>l.id==='hotspots'),high=style.layers.find(l=>l.id==='high-fire');
  assert.equal(points.type,'circle');assert.ok(JSON.stringify(points.paint).includes('industrial'));
  assert.equal(high.type,'circle');assert.ok(JSON.stringify(high.filter).includes('industrial'));
  assert.ok(!JSON.stringify(style).includes('fire-emoji'));
});
