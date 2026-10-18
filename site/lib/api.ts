import { env } from "cloudflare:workers";
import { collectorBatch,operatorBatch,sourceStatus } from "./validation";
const sources={VIIRS_NOAA21_NRT:"NOAA-21 · VIIRS",VIIRS_NOAA20_NRT:"NOAA-20 · VIIRS",VIIRS_SNPP_NRT:"Suomi-NPP · VIIRS",MODIS_NRT:"Terra / Aqua · MODIS"};
const json=(body:any,status=200)=>Response.json(body,{status,headers:{"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}});
async function equal(a:string,b:string) {
  if(!b)return false;
  const digest=async(v:string)=>new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(v)));
  const [x,y]=await Promise.all([digest(a),digest(b)]);let diff=0;for(let i=0;i<x.length;i++)diff|=x[i]^y[i];return diff===0;
}
async function list(kind:string) {
  const result=await env.DB!.prepare("SELECT body FROM records WHERE kind=? ORDER BY updated_at DESC LIMIT 1000").bind(kind).all<{body:string}>();
  return result.results.map(x=>JSON.parse(x.body));
}
async function published() {return (await list("incidents")).filter(x=>x.review_state==="published");}
export async function handle(request:Request) {
  const response=await route(request);
  if(request.method==='GET'&&request.headers.get('Origin')==='https://kletterrn.github.io') {
    response.headers.set('Access-Control-Allow-Origin','https://kletterrn.github.io');
    response.headers.set('Vary','Origin');
  }
  return response;
}
async function route(request:Request) {
  try {
    if(!env.DB)return json({error:"Database configuration unavailable"},503);
    const url=new URL(request.url), path=url.pathname;
    if(request.method==="POST"&&path==="/api/v1/ingest") {
      const token=request.headers.get("Authorization")?.replace(/^Bearer /,"")||"";
      const runtime=env as any;
      const role=await equal(token,runtime.IGNIS_COLLECTOR_TOKEN||"")?"collector":await equal(token,runtime.IGNIS_OPERATOR_TOKEN||"")?"operator":null;
      if(!role)return json({error:"Unauthorized"},401);
      if(request.headers.get("Origin"))return json({error:"Service endpoint does not accept browser origins"},403);
      if(!request.headers.get("Content-Type")?.includes("application/json"))return json({error:"JSON required"},415);
      const bytes=await request.arrayBuffer();if(bytes.byteLength>4_000_000)return json({error:"Payload too large"},413);
      const schema=role==="collector"?collectorBatch:operatorBatch;
      const parsed=schema.safeParse(JSON.parse(new TextDecoder().decode(bytes)));
      if(!parsed.success)return json({error:"Invalid batch",issues:parsed.error.issues.map(x=>({path:x.path,message:x.message})).slice(0,10)},400);
      const body=parsed.data as any, now=new Date().toISOString();
      if(role==="operator") {
        const ids=new Set(body.incidents.map((x:any)=>x.id));
        for(const p of body.perimeters)if(!ids.has(p.incident_id))return json({error:"Perimeter incident missing from batch"},400);
        for(const e of body.evidence||[])if(!ids.has(e.incident_id))return json({error:"Evidence incident missing"},400);
        if(body.evidence?.length&&!env.BUCKET)return json({error:"Evidence storage unavailable"},503);
        for(const e of body.evidence||[]) {
          const raw=Uint8Array.from(atob(e.jpeg),(c:string)=>c.charCodeAt(0));
          if(raw.length>350000||raw[0]!==255||raw[1]!==216)return json({error:"Invalid JPEG evidence"},400);
          await env.BUCKET!.put(e.id+".jpg",raw,{httpMetadata:{contentType:"image/jpeg"},customMetadata:{incident_id:e.incident_id}});
        }
      }
      const statements=[];
      for(const kind of ["observations","sources","weather","incidents","perimeters"])for(const item of body[kind]||[]) {
        statements.push(env.DB.prepare("INSERT INTO records(kind,id,body,acquired_at,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body,acquired_at=excluded.acquired_at,updated_at=excluded.updated_at").bind(kind,item.id,JSON.stringify(item),item.acquired_at||null,now));
      }
      if(body.evidence?.length)for(const e of body.evidence)statements.push(env.DB.prepare("INSERT INTO records(kind,id,body,updated_at) VALUES('evidence',?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body,updated_at=excluded.updated_at").bind(e.id,JSON.stringify({id:e.id,incident_id:e.incident_id}),now));
      statements.push(env.DB.prepare("DELETE FROM records WHERE kind='observations' AND acquired_at < ?").bind(new Date(Date.now()-90*86400000).toISOString()));
      await env.DB.batch(statements);
      return json({status:"accepted",records:statements.length-1});
    }
    if(request.method!=="GET")return json({error:"Method not allowed"},405);
    if(path==="/api/observations") {
      const hours=Number(url.searchParams.get("hours")||24);
      const selected=[...new Set((url.searchParams.get("sources")||"VIIRS_NOAA21_NRT").split(","))];
      if(![1,6,12,24].includes(hours)||selected.some(s=>!(s in sources)))return json({error:"Invalid time window or source"},400);
      const now=new Date().toISOString(),cutoff=new Date(Date.now()-hours*3600000).toISOString();
      const raw=await env.DB.prepare("SELECT body FROM records WHERE kind='observations' AND acquired_at>=? AND acquired_at<=? ORDER BY acquired_at DESC LIMIT 20000").bind(cutoff,now).all<{body:string}>();
      const observations=raw.results.map(x=>JSON.parse(x.body)).filter(x=>selected.includes(x.dataset));
      const all=await list("sources");
      const states=selected.map(id=>sourceStatus(all.find(x=>x.id===id)||{id,label:(sources as any)[id],status:"configuration_missing",count:0}));
      const good=states.filter(x=>x.status==="connected").length;
      return json({observations,sources:states,status:good===states.length?"connected":good?"partial":states.every(x=>x.status==="configuration_missing")?"configuration_missing":"unavailable",checked_at:states.map(x=>x.checked_at||"").sort().at(-1)||null,hours,source:selected.join(","),area:"5.8,47.2,15.1,55.1",truncated:raw.results.length===20000,message:"Satellitenbeobachtungen · keine Brandbestätigung"});
    }
    if(path==="/api/v1/health")return json({sources:(await list("sources")).map(x=>sourceStatus(x)),checked_at:new Date().toISOString()});
    if(path==="/api/v1/weather")return json({weather:await list("weather")});
    if(path==="/api/v1/incidents")return json({incidents:await published()});
    if(path==="/api/v1/perimeters") {
      const ids=new Set((await published()).map(x=>x.id));
      return json({perimeters:(await list("perimeters")).filter(x=>ids.has(x.incident_id)&&x.review_state==="approved")});
    }
    if(path==="/api/v1/evidence") {
      const ids=new Set((await published()).map(x=>x.id));
      return json({evidence:(await list("evidence")).filter(x=>ids.has(x.incident_id))});
    }
    if(path.startsWith("/api/v1/evidence/")) {
      const key=path.split("/").at(-1)!;
      if(!/^[a-zA-Z0-9_-]{1,100}$/.test(key))return json({error:"Not found"},404);
      const record=(await list("evidence")).find(x=>x.id===key);
      if(!record||!(await published()).some(x=>x.id===record.incident_id))return json({error:"Not found"},404);
      const object=await env.BUCKET?.get(key+".jpg");if(!object)return json({error:"Not found"},404);
      return new Response(object.body,{headers:{"Content-Type":"image/jpeg","Cache-Control":"no-store","X-Content-Type-Options":"nosniff"}});
    }
    return json({error:"Not found"},404);
  }catch(error){console.error("Ignis API failure",error instanceof Error?error.name+": "+error.message.slice(0,200):"Unknown error");return json({error:"Service temporarily unavailable"},503);}
}
