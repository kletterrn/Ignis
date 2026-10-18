/* Evidence screening only: nearby thermal observations do not establish wildfire. */
(function(root){
  'use strict';
  const confidence=typeof module!=='undefined'&&module.exports?require('./hotzones.js').confidence:root.IgnisZones.confidence;
  function time(o){return Date.parse(String(o.detected_at).replace(' UTC','Z').replace(' ','T'));}
  function distance(a,b){
    const rad=Math.PI/180, lat=(b.latitude-a.latitude)*rad, lon=(b.longitude-a.longitude)*rad;
    const h=Math.sin(lat/2)**2+Math.cos(a.latitude*rad)*Math.cos(b.latitude*rad)*Math.sin(lon/2)**2;
    return 6371*2*Math.asin(Math.sqrt(Math.min(1,h)));
  }
  function assessObservations(observations){
    return observations.map(o=>{
      const supports=observations.filter(other=>other!==o && o.satellite && other.satellite && other.satellite!==o.satellite && confidence(o.confidence)!=='low' && confidence(other.confidence)!=='low' && Math.abs(time(other)-time(o))<=3*3600000 && distance(o,other)<=1);
      const satellites=[...new Set(supports.map(other=>other.satellite))];
      return {...o,verification:supports.length?'Cross-satellite support':'Unverified',verification_detail:supports.length?`${supports.length} nahe Wärmehinweise von ${satellites.join(', ')} im Umkreis von 1 km und ±3 Stunden. Nächster Hinweis: ${Math.min(...supports.map(other=>distance(o,other))).toFixed(2)} km entfernt. Zeiten: ${[...new Set(supports.map(other=>other.detected_at))].join('; ')}. Das unterstützt den Hinweis auf eine Wärmequelle, nicht zwingend auf einen Waldbrand.`:'Kein passender Hinweis eines anderen Satelliten innerhalb von 1 km und ±3 Stunden. Das bedeutet nicht, dass der Hinweis falsch ist.'};
    });
  }
  const api={assessObservations};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.IgnisVerification=api;
})(typeof window!=='undefined'?window:globalThis);
