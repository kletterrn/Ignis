import os
from pathlib import Path
import httpx
import numpy as np
import rasterio
from rasterio.features import shapes
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from shapely.geometry import shape, mapping
from shapely.ops import transform, unary_union
from pyproj import Transformer
from services.geometry import measure, polygon, timestamp

CDSE = "https://sh.dataspace.copernicus.eu"

def search_scenes(bbox, start, end):
    polygon({"type": "Polygon", "coordinates": [[[bbox[0],bbox[1]],[bbox[2],bbox[1]],[bbox[2],bbox[3]],[bbox[0],bbox[3]],[bbox[0],bbox[1]]]]})
    timestamp(start); timestamp(end)
    r = httpx.post("https://stac.dataspace.copernicus.eu/v1/search", json={"collections": ["sentinel-2-l2a"], "bbox": bbox, "datetime": f"{start}/{end}", "limit": 20}, timeout=40)
    r.raise_for_status()
    return [{"id": x["id"], "acquired_at": x["properties"]["datetime"], "cloud_cover": x["properties"].get("eo:cloud_cover"), "geometry": x["geometry"]} for x in r.json()["features"]]

def download_scene(bbox, acquired_at, destination):
    from datetime import timedelta
    instant = timestamp(acquired_at)
    client, secret = os.getenv("CDSE_CLIENT_ID"), os.getenv("CDSE_CLIENT_SECRET")
    if not client or not secret:
        raise ValueError("Copernicus OAuth client credentials missing")
    w, s, e, n = bbox
    polygon({"type":"Polygon","coordinates":[[[w,s],[e,s],[e,n],[w,n],[w,s]]]})
    # Bound local memory and processing-unit use to an incident-sized request.
    width = max(1, math_ceil((e-w)*111320*np.cos(np.deg2rad((s+n)/2))/20))
    height = max(1, math_ceil((n-s)*111320/20))
    if width * height > 4_000_000:
        raise ValueError("Area exceeds 4 million 20 m pixels; choose a smaller incident region")
    auth = httpx.post("https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token", data={"grant_type":"client_credentials", "client_id":client, "client_secret":secret}, timeout=30)
    auth.raise_for_status()
    script = '//VERSION=3\nfunction setup(){return {input:["B08","B12","SCL","dataMask"],output:{bands:4,sampleType:"FLOAT32"}}} function evaluatePixel(s){return [s.B08,s.B12,s.SCL,s.dataMask]}'
    body = {"input":{"bounds":{"bbox":bbox},"data":[{"type":"sentinel-2-l2a","dataFilter":{"timeRange":{"from":instant.isoformat(),"to":(instant+timedelta(seconds=1)).isoformat()},"mosaickingOrder":"mostRecent"}}]},"output":{"width":width,"height":height,"responses":[{"identifier":"default","format":{"type":"image/tiff"}}]},"evalscript":script}
    r = httpx.post(CDSE+"/process/v1", headers={"Authorization":"Bearer "+auth.json()["access_token"]}, json=body, timeout=120)
    r.raise_for_status()
    Path(destination).write_bytes(r.content)
    return str(destination)

def math_ceil(x):
    return int(np.ceil(x))

def burned_outline(before_path, after_path, threshold=.2):
    if not .05 <= threshold <= 1:
        raise ValueError("dNBR threshold must be between .05 and 1")
    with rasterio.open(before_path) as pre, rasterio.open(after_path) as post:
        if not pre.crs or not post.crs or pre.count < 4 or post.count < 4:
            raise ValueError("Georeferenced four-band B08/B12/SCL/dataMask rasters required")
        if post.width * post.height > 4_000_000:
            raise ValueError("Raster exceeds 4 million pixels")
        if pre.count > 8 or post.count > 8:
            raise ValueError("Unexpected band count")
        before = np.zeros((4, post.height, post.width), dtype="float32")
        for band in range(4):
            reproject(rasterio.band(pre, band+1), before[band], src_transform=pre.transform, src_crs=pre.crs, dst_transform=post.transform, dst_crs=post.crs, resampling=Resampling.nearest if band >= 2 else Resampling.bilinear)
        after = post.read([1,2,3,4])
        valid = np.isin(before[2], [4,5]) & np.isin(after[2], [4,5]) & (before[3] > .5) & (after[3] > .5)
        valid &= np.isfinite(before).all(axis=0) & np.isfinite(after).all(axis=0) & ((before[0]+before[1]) > 0) & ((after[0]+after[1]) > 0)
        if valid.sum() == 0:
            raise ValueError("No common clear coverage; movement cannot be determined")
        nbr_before = (before[0]-before[1]) / np.maximum(before[0]+before[1], 1e-6)
        nbr_after = (after[0]-after[1]) / np.maximum(after[0]+after[1], 1e-6)
        mask = valid & ((nbr_before-nbr_after) >= threshold)
        project = Transformer.from_crs(post.crs, 4326, always_xy=True).transform
        def vectorize(mask):
            geoms = [shape(g) for g, value in shapes(mask.astype("uint8"), mask=mask, transform=post.transform) if value == 1]
            return transform(project, unary_union(geoms))
        if not mask.any():
            raise ValueError("No candidate burned area at this threshold")
        result = measure(mapping(vectorize(mask)))
        coverage = vectorize(valid)
        result.update(coverage=mapping(coverage), clear_coverage_fraction=float(valid.mean()), method="Sentinel-2 dNBR", threshold=threshold, resolution_m=20, footprint_kind="burned", review_state="draft")
        return result

def inspect_orthomosaic(path):
    with rasterio.open(path) as src:
        if not src.crs or src.width*src.height > 100_000_000:
            raise ValueError("Georeferencing required; raster limit 100 million pixels")
        bounds = transform_bounds(src.crs, 4326, *src.bounds)
        w,s,e,n = bounds
        bounds_geometry = {"type":"Polygon","coordinates":[[[w,s],[e,s],[e,n],[w,n],[w,s]]]}
        polygon(bounds_geometry)
        mask=src.dataset_mask(out_shape=(512,512))>0
        if not mask.any():raise ValueError('Raster contains no valid observed pixels')
        from affine import Affine
        preview_transform=src.transform*Affine.scale(src.width/512,src.height/512)
        footprint=unary_union([shape(g) for g,v in shapes(mask.astype('uint8'),mask=mask,transform=preview_transform) if v==1])
        to_wgs84=Transformer.from_crs(src.crs,4326,always_xy=True).transform
        coverage=mapping(transform(to_wgs84,footprint))
        data = src.read(list(range(1,min(src.count,3)+1)), out_shape=(min(src.count,3),512,512), resampling=Resampling.bilinear)
        if len(data) == 1:
            data = np.repeat(data,3,axis=0)
        elif len(data) == 2:
            data = np.concatenate([data,data[:1]])
        rgb = np.moveaxis(data,0,-1).astype(float)
        lo,hi = np.nanpercentile(rgb,[2,98])
        rgb = np.clip((rgb-lo)/max(hi-lo,1e-6)*255,0,255).astype("uint8")
        from PIL import Image
        preview = str(Path(path).with_suffix(".png"))
        Image.fromarray(rgb).save(preview)
        return {"coverage":coverage,"preview":preview,"bounds":bounds,"crs":src.crs.to_string(),"width":src.width,"height":src.height,"note":"Preview is for tracing; source raster remains local"}
