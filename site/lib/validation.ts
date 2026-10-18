import { z } from "zod";
const id = z.string().regex(/^[A-Za-z0-9_-]{1,100}$/);
const time = z.string().datetime({offset:true}).transform(value=>new Date(value).toISOString());
const number = z.number().finite();
const coordinate = z.tuple([number.min(5).max(16),number.min(46).max(56)]);
const ring = z.array(coordinate).min(4).max(2000).refine(r=>r[0][0]===r.at(-1)![0]&&r[0][1]===r.at(-1)![1],"Ring must be closed");
const rings = z.array(ring).min(1).max(100);
export const geometry = z.discriminatedUnion("type",[
  z.object({type:z.literal("Polygon"),coordinates:rings}).strict(),
  z.object({type:z.literal("MultiPolygon"),coordinates:z.array(rings).min(1).max(100)}).strict(),
]);
const observation=z.object({id,latitude:number.min(-90).max(90),longitude:number.min(-180).max(180),acquired_at:time,retrieved_at:time,detected_at:z.string().max(40),source:z.literal("NASA_FIRMS"),dataset:z.enum(["VIIRS_NOAA21_NRT","VIIRS_NOAA20_NRT","VIIRS_SNPP_NRT","MODIS_NRT"]),satellite:z.string().max(40),sensor:z.string().max(40),confidence:z.string().max(20),frp:number.min(0),daynight:z.string().max(2),scan_km:number.positive().max(10).optional(),track_km:number.positive().max(10).optional(),thermal_type:z.number().int().min(0).max(3).optional(),context_kind:z.enum(["unknown","industrial","static_source"]).optional(),context_name:z.string().max(100).optional(),context_source:z.string().max(200).optional(),context_checked_at:time.nullable().optional(),context_distance_m:number.min(0).max(1000).optional()}).strict();
const source=z.object({id,label:z.string().max(100).optional(),status:z.enum(["connected","unavailable","configuration_missing"]),checked_at:time,last_success_at:time.nullable().optional(),count:z.number().int().min(0).optional()}).strict();
const current=z.object({time:z.string().max(40),interval:number,temperature_2m:number.nullable(),relative_humidity_2m:number.min(0).max(100).nullable(),precipitation:number.min(0).nullable(),wind_speed_10m:number.min(0).nullable(),wind_direction_10m:number.min(0).max(360).nullable(),wind_gusts_10m:number.min(0).nullable()}).strict();
const weather=z.object({id,latitude:number.min(-90).max(90),longitude:number.min(-180).max(180),retrieved_at:time,current,hourly:z.record(z.array(z.union([number,z.string().max(40),z.null()])).max(200)),units:z.record(z.string().max(40)),model:z.string().max(100),attribution:z.string().max(100),modeled:z.literal(true)}).strict();
const incident=z.object({id,title:z.string().min(1).max(120),description:z.string().max(2000),created_at:time,updated_at:time,review_state:z.enum(["published","withdrawn"])}).strict();
const change=z.object({status:z.enum(["measured","insufficient_evidence"]),kind:z.string().optional(),message:z.string().max(300),reason:z.string().max(300).optional(),added_geometry:geometry.nullable().optional(),added_area_ha:number.min(0).optional(),elapsed_hours:number.positive().optional(),area_growth_ha_per_hour:number.min(0).optional(),sectors_ha:z.record(number.min(0)).optional(),dominant_sector:z.enum(["N","NE","E","SE","S","SW","W","NW"]).nullable().optional()}).strict();
const perimeter=z.object({id,incident_id:id,geometry,coverage:geometry,burned_area_ha:number.positive(),enclosed_area_ha:number.positive(),area_crs:z.literal("EPSG:3035"),acquired_at:time,created_at:time,reviewed_at:time,review_state:z.literal("approved"),method:z.string().max(80),resolution_m:number.positive().max(1000).nullable(),footprint_kind:z.enum(["burned","active"]),provenance:z.string().max(500),change:change.optional()}).strict();
export const collectorBatch=z.object({observations:z.array(observation).max(250),sources:z.array(source).max(100),weather:z.array(weather).max(100)}).strict();
export const operatorBatch=z.object({incidents:z.array(incident).max(20),perimeters:z.array(perimeter).max(100),evidence:z.array(z.object({id,incident_id:id,jpeg:z.string().max(500000)}).strict()).max(5).optional()}).strict();
export function sourceStatus(s:any,now=Date.now()) {
  return {...s,status:s.last_success_at&&now-Date.parse(s.last_success_at)>45*60000?"stale":s.status};
}
