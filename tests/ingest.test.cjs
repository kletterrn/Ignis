const {test}=require('node:test');
const assert=require('node:assert/strict');

test('collector keeps legacy payloads and validates industrial context and sensor dimensions',async()=>{
  const {collectorBatch}=await import('../site/lib/validation.ts');
  const observation={id:'source_1',latitude:50,longitude:10,acquired_at:'2026-10-18T12:00:00Z',retrieved_at:'2026-10-18T12:01:00Z',detected_at:'2026-10-18 12:00 UTC',source:'NASA_FIRMS',dataset:'VIIRS_NOAA21_NRT',satellite:'N21',sensor:'VIIRS',confidence:'n',frp:4,daynight:'D'};
  const batch=o=>({observations:[o],sources:[],weather:[]});
  assert.ok(collectorBatch.safeParse(batch(observation)).success);
  assert.ok(collectorBatch.safeParse(batch({...observation,scan_km:.4,track_km:.6,context_kind:'industrial',context_name:'Registered works',context_distance_m:200,context_checked_at:'2026-10-18T12:01:00Z'})).success);
  for(const extra of [{scan_km:-1},{context_distance_m:1001},{context_kind:'confirmed_fire'},{private_token:'must not be accepted'}]){
    assert.equal(collectorBatch.safeParse(batch({...observation,...extra})).success,false);
  }
});
