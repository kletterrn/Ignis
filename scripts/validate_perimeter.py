"""Compare a candidate against an independently sourced dated reference polygon."""
import argparse,json
from pathlib import Path
from shapely.ops import transform
from services.geometry import polygon,TO_METERS

def main():
    p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('reference');args=p.parse_args()
    a,b=[transform(TO_METERS,polygon(json.loads(Path(x).read_text(encoding='utf-8')))) for x in (args.candidate,args.reference)]
    print(json.dumps({'intersection_over_union':a.intersection(b).area/a.union(b).area,'candidate_area_ha':a.area/10000,'reference_area_ha':b.area/10000,'relative_area_error':abs(a.area-b.area)/b.area,'hausdorff_distance_m':a.hausdorff_distance(b),'note':'Only compare equivalent footprint definitions, coverage and acquisition dates.'},indent=2))

if __name__=='__main__':main()
