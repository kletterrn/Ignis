/* Basemaps and fire overlays are composed together, including on style switches. */
(function(root) {
  'use strict';
  const overlayIds=['zone-fill','zone-outline','clusters','hotspot-glow','hotspots','high-fire','cluster-count'];
  function localNames(value) {
    if(typeof value==='string') return value.replaceAll('{name_en}','{name}');
    if(Array.isArray(value)) return value.map(localNames);
    if(value && typeof value==='object') return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,localNames(item)]));
    return value;
  }
  function germanStyle(base) {
    return {...base,layers:base.layers.map(layer=>layer.layout?.['text-field']?{...layer,layout:{...layer.layout,'text-field':localNames(layer.layout['text-field'])}}:layer)};
  }
  function imageryStyle() {
    return {version:8,glyphs:'https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf',sources:{imagery:{type:'raster',tiles:['https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],tileSize:256,maxzoom:19,attribution:'Imagery © <a href="https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9">Esri</a>, Vantor, Earthstar Geographics, and the GIS User Community'}},layers:[{id:'imagery',type:'raster',source:'imagery'}]};
  }
  function composeStyle(base,detections,zones,showHotspots,showZones) {
    const points=showHotspots?'visible':'none',areas=showZones?'visible':'none';
    const unclustered=['!',['has','point_count']];
    const color=['match',['get','level'],'high','#ff8853','nominal','#eabf69','#a6b49c'];
    return {...base,sources:{...base.sources,'hot-zones':{type:'geojson',data:zones},detections:{type:'geojson',data:detections,cluster:true,clusterMaxZoom:11,clusterRadius:35}},layers:[...base.layers.filter(layer=>!overlayIds.includes(layer.id)),
      {id:'zone-fill',type:'fill',source:'hot-zones',layout:{visibility:areas},paint:{'fill-color':'#ff6c42','fill-opacity':.22}},
      {id:'zone-outline',type:'line',source:'hot-zones',layout:{visibility:areas},paint:{'line-color':'#ff995e','line-width':2,'line-dasharray':[3,2]}},
      {id:'clusters',type:'circle',source:'detections',filter:['has','point_count'],layout:{visibility:points},paint:{'circle-color':'#fc925c','circle-radius':['step',['get','point_count'],12,10,17,50,23],'circle-opacity':.9,'circle-stroke-width':6,'circle-stroke-color':'#fc925c','circle-stroke-opacity':.16}},
      {id:'hotspot-glow',type:'circle',source:'detections',filter:unclustered,layout:{visibility:points},paint:{'circle-color':color,'circle-radius':13,'circle-opacity':.2}},
      {id:'hotspots',type:'circle',source:'detections',filter:['all',unclustered,['!=',['get','level'],'high']],layout:{visibility:points},paint:{'circle-color':color,'circle-radius':5,'circle-stroke-color':'#fff0d9','circle-stroke-width':1.5}},
      {id:'high-fire',type:'symbol',source:'detections',filter:['all',unclustered,['==',['get','level'],'high']],layout:{visibility:points,'icon-image':'fire-emoji','icon-size':0.5,'icon-allow-overlap':true,'icon-ignore-placement':true}},
      {id:'cluster-count',type:'symbol',source:'detections',filter:['has','point_count'],layout:{visibility:points,'text-field':['get','point_count_abbreviated'],'text-font':['Noto Sans Regular'],'text-size':11},paint:{'text-color':'#142019'}}
    ]};
  }
  // Only the latest requested basemap may win, even when network responses arrive out of order.
  function createStyleSwitcher(load,apply) {
    let revision=0;
    return async name=>{
      const current=++revision;
      try { const style=await load(name);if(current!==revision)return false;apply(style,name);return true; }
      catch(error){if(current===revision)throw error;return false;}
    };
  }
  const api={composeStyle,germanStyle,imageryStyle,createStyleSwitcher};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.IgnisMaps=api;
})(typeof window!=='undefined'?window:globalThis);
