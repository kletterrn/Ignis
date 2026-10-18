const {test}=require('node:test');
const assert=require('node:assert/strict');
const {composeStyle,createStyleSwitcher}=require('../static/maps.js');
const empty={type:'FeatureCollection',features:[]};
const base={version:8,sources:{base:{type:'raster',tiles:['https://example.com/{z}/{x}/{y}.png']}},layers:[{id:'base',source:'base',type:'raster'}]};

test('3D uses real Terrarium heights at 1:1 and preserves fire overlays and filters',()=>{
  const style=composeStyle(base,empty,empty,false,true,true);
  assert.deepEqual(style.terrain,{source:'terrain-dem',exaggeration:1});
  assert.equal(style.sources['terrain-dem'].encoding,'terrarium');
  assert.equal(style.sources['terrain-dem'].maxzoom,15);
  assert.equal(style.layers.find(l=>l.id==='hotspots').layout.visibility,'none');
  assert.equal(style.layers.find(l=>l.id==='zone-fill').layout.visibility,'visible');
  assert.ok(style.sources.base&&style.sources.detections&&style.sources['hot-zones']);
  assert.equal(base.sources['terrain-dem'],undefined);
  const flat=composeStyle(base,empty,empty,true,true,false);
  assert.equal(flat.terrain,undefined);
  assert.equal(flat.sources['terrain-dem'],undefined);
});

test('latest style request wins and reads current terrain/filter state',async()=>{
  let release,terrain=false,result;
  const switchStyle=createStyleSwitcher(name=>name==='slow'?new Promise(resolve=>release=resolve):Promise.resolve(base),style=>result=composeStyle(style,empty,empty,true,true,terrain));
  const slow=switchStyle('slow');terrain=true;
  assert.equal(await switchStyle('fast'),true);release(base);
  assert.equal(await slow,false);
  assert.equal(result.terrain.exaggeration,1);
});
