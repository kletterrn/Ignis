"""Local calibrated sensor products. Never infer geolocation from camera position."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from services.geometry import measure, polygon, timestamp


def digest(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stereo_measure(left_path, right_path, calibration, left_at, right_at, destination):
    import cv2
    left_time, right_time = timestamp(left_at), timestamp(right_at)
    if abs((left_time-right_time).total_seconds()) > .05:
        raise ValueError('Stereo timestamps differ by more than 50 ms')
    if not calibration.get('calibration_id') or calibration.get('translation_unit') != 'm':
        raise ValueError('Calibration ID and translation_unit=m required')
    if timestamp(calibration['calibrated_at']) > min(left_time, right_time):
        raise ValueError('Calibration must precede acquisition')
    rms = float(calibration['rms_px'])
    if not np.isfinite(rms) or not 0 <= rms <= 2:
        raise ValueError('Calibration reprojection RMS must be 0–2 px; field validation still required')
    def matrix(key, size):
        value = np.asarray(calibration[key], dtype='float64')
        if value.shape != size or not np.isfinite(value).all():
            raise ValueError('Invalid calibration matrix '+key)
        return value
    k1, k2, rotation = matrix('K1', (3,3)), matrix('K2', (3,3)), matrix('R', (3,3))
    translation = matrix('T', (3,))
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(rotation), 1, atol=1e-5):
        raise ValueError('R must be a proper rotation matrix')
    for k in (k1,k2):
        if k[0,0] <= 0 or k[1,1] <= 0 or not np.allclose(k[2], [0,0,1]):
            raise ValueError('Invalid pinhole intrinsics')
    baseline = float(np.linalg.norm(translation))
    if not .001 <= baseline <= 100 or translation[0] >= 0 or abs(translation[0]) < max(abs(translation[1]),abs(translation[2])):
        raise ValueError('Horizontal left-to-right stereo rig with negative T.x in metres required')
    distortions=[]
    for key in ('D1','D2'):
        d=np.asarray(calibration[key],dtype='float64')
        if d.ndim != 1 or len(d) not in (4,5,8,12,14) or not np.isfinite(d).all():
            raise ValueError('Invalid distortion coefficients')
        distortions.append(d)
    images=[]
    for path in (left_path,right_path):
        with Image.open(path) as image:
            if image.width*image.height > 2_000_000 or image.width > 2048 or image.width < 160 or image.height < 32:
                raise ValueError('Stereo image limit: 2 million pixels, width 160–2048')
            images.append(np.asarray(image.convert('RGB')))
    size=(images[0].shape[1],images[0].shape[0])
    if images[0].shape != images[1].shape or list(size) != calibration['image_size']:
        raise ValueError('Both images must match the calibrated image_size; resizing is not allowed')
    r1,r2,p1,p2,q,roi1,roi2=cv2.stereoRectify(k1,distortions[0],k2,distortions[1],size,rotation,translation,flags=cv2.CALIB_ZERO_DISPARITY,alpha=0)
    rectified=[]
    for image,k,d,r,p in zip(images,(k1,k2),distortions,(r1,r2),(p1,p2)):
        mx,my=cv2.initUndistortRectifyMap(k,d,r,p,size,cv2.CV_32FC1)
        rectified.append(cv2.remap(image,mx,my,cv2.INTER_LINEAR))
    gray=[cv2.cvtColor(image,cv2.COLOR_RGB2GRAY) for image in rectified]
    disparities=min(128, ((size[0]//3)//16)*16)
    def disparity(a,b,minimum):
        matcher=cv2.StereoSGBM_create(minDisparity=minimum,numDisparities=disparities,blockSize=5,P1=8*25,P2=32*25,uniquenessRatio=15,speckleWindowSize=100,speckleRange=2,disp12MaxDiff=1)
        return matcher.compute(a,b).astype('float32')/16
    left=disparity(gray[0],gray[1],0);right=disparity(gray[1],gray[0],-disparities)
    yy,xx=np.indices(left.shape);rx=np.rint(xx-left).astype(int)
    in_bounds=(rx>=0)&(rx<size[0]);sample=right[yy,np.clip(rx,0,size[0]-1)]
    valid=in_bounds&(left>0)&(sample<0)&(np.abs(left+sample)<=1)
    for index,roi in enumerate((roi1,roi2)):
        x,y,w,h=roi
        # Both rectified image ROIs must contain their corresponding match.
        coord=xx if index==0 else rx
        valid &= (coord>=x)&(coord<x+w)&(yy>=y)&(yy<y+h)
    xyz=cv2.reprojectImageTo3D(left,q)
    valid &= np.isfinite(xyz).all(axis=2)&(xyz[:,:,2]>.05)&(xyz[:,:,2]<=2000)
    if valid.sum()<100:
        raise ValueError('Insufficient consistent stereo matches; no depth measurement available')
    root=Path(destination);root.mkdir(parents=True,exist_ok=True)
    depth=np.where(valid,xyz[:,:,2],np.nan).astype('float32')
    np.savez_compressed(root/'depth.npz',depth_m=depth,valid=valid,Q=q)
    points=xyz[valid];colors=rectified[0][valid];step=max(1,int(np.ceil(len(points)/100_000)))
    export=np.column_stack((points[::step],colors[::step]))
    with (root/'points.ply').open('w',encoding='ascii') as out:
        out.write(f'ply\nformat ascii 1.0\ncomment rectified left-camera coordinates in metres; not georeferenced\nelement vertex {len(export)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
        np.savetxt(out,export,fmt=['%.5f','%.5f','%.5f','%d','%d','%d'])
    depths=depth[valid];lo,hi=np.percentile(depths,[2,98]);shade=np.zeros_like(depth,dtype='uint8')
    shade[valid]=np.clip((depths-lo)/max(float(hi-lo),1e-6)*255,0,255).astype('uint8')
    preview=cv2.applyColorMap(shade,cv2.COLORMAP_TURBO);preview[~valid]=0
    cv2.imwrite(str(root/'preview.png'),preview)
    preview_step=max(1,int(np.ceil(len(export)/2500)))
    return {'kind':'stereo','review_state':'unvalidated','georeferenced':False,'acquired_at':left_time.isoformat(),
            'calibration_id':str(calibration['calibration_id'])[:120],'calibrated_at':calibration['calibrated_at'],'calibration_rms_px':rms,'baseline_m':baseline,
            'sync_delta_ms':abs((left_time-right_time).total_seconds())*1000,'valid_fraction':float(valid.mean()),
            'depth_m':{'min':float(depths.min()),'median':float(np.median(depths)),'max':float(depths.max())},
            'preview_scale_m':{'near_blue':float(lo),'far_red':float(hi)},
            'coordinate_frame':'rectified left camera: x right, y down, z forward; metres',
            'input_sha256':[digest(left_path),digest(right_path)],
            'calibration_sha256':hashlib.sha256(json.dumps(calibration,sort_keys=True).encode()).hexdigest(),
            'points_preview':export[::preview_step].round(5).tolist(),
            'note':'Scene depth from supplied calibration, not fire height/volume/location. Smoke, reflections and motion can invalidate matches. No field accuracy established.'}


def thermal_measure(path, threshold_c, destination):
    import rasterio
    from rasterio.features import shapes
    from pyproj import Transformer
    from shapely.geometry import shape,mapping
    from shapely.ops import unary_union,transform
    threshold=float(threshold_c)
    if not np.isfinite(threshold) or not -100<=threshold<=2000:
        raise ValueError('Temperature threshold must be -100–2000 Celsius')
    with rasterio.open(path) as src:
        tags=src.tags()
        if src.count!=1 or not src.crs or src.width*src.height>4_000_000 or abs(src.transform.determinant)<1e-15:
            raise ValueError('Georeferenced single-band radiometric GeoTIFF required; limit 4 million pixels')
        for key in ('TEMPERATURE_UNIT','SENSOR_ID','CALIBRATION_ID','CALIBRATED_AT','ACQUIRED_AT','TEMPERATURE_KIND'):
            if not tags.get(key):raise ValueError('Required radiometric metadata missing: '+key)
        if tags['TEMPERATURE_UNIT'] not in ('Celsius','Kelvin') or tags['TEMPERATURE_KIND']!='apparent':
            raise ValueError('Supported input: calibrated apparent temperature in Celsius or Kelvin; palette imagery is unsupported')
        acquired=timestamp(tags['ACQUIRED_AT'])
        if timestamp(tags['CALIBRATED_AT'])>acquired:raise ValueError('Calibration must precede acquisition')
        raw=src.read(1,masked=True);scale,offset=src.scales[0],src.offsets[0]
        if not np.isfinite([scale,offset]).all() or scale<=0:raise ValueError('Invalid radiometric scale/offset')
        temp=raw.astype('float64').filled(np.nan)*scale+offset-(273.15 if tags['TEMPERATURE_UNIT']=='Kelvin' else 0)
        valid=~np.ma.getmaskarray(raw)&np.isfinite(temp)
        if not valid.any():raise ValueError('No valid temperature pixels')
        if (temp[valid]<-273.15).any() or (temp[valid]>3000).any():raise ValueError('Temperature outside supported physical range; check units and calibration')
        hot=valid&(temp>=threshold)
        project=Transformer.from_crs(src.crs,4326,always_xy=True).transform
        def vectorize(mask):
            pieces=[]
            for g,v in shapes(mask.astype('uint8'),mask=mask,transform=src.transform):
                if v==1:pieces.append(shape(g))
                if len(pieces)>10_000:raise ValueError('Too many thermal fragments; use a smaller region')
            if not pieces:return None
            result=mapping(transform(project,unary_union(pieces)));polygon(result)
            return result
        coverage=vectorize(valid);candidate=vectorize(hot)
        area=measure(candidate)['burned_area_ha'] if candidate else 0
        root=Path(destination);root.mkdir(parents=True,exist_ok=True)
        lo,hi=np.percentile(temp[valid],[2,98]);rgb=np.zeros((*temp.shape,3),dtype='uint8')
        shade=np.clip((np.nan_to_num(temp,nan=lo)-lo)/max(float(hi-lo),1e-6)*255,0,255).astype('uint8')
        rgb[:]=np.stack((shade,shade,shade),axis=-1);rgb[hot]=[255,70,25];rgb[~valid]=0
        image=Image.fromarray(rgb);image.thumbnail((1024,1024));image.save(root/'preview.png')
        feature={'type':'Feature','geometry':candidate,'properties':{'kind':'thermal_threshold_candidate','threshold_c':threshold,'review_state':'unvalidated','acquired_at':acquired.isoformat()}}
        (root/'hot.geojson').write_text(json.dumps(feature),encoding='utf-8')
        values=temp[valid]
        return {'kind':'thermal','review_state':'unvalidated','georeferenced':True,'acquired_at':acquired.isoformat(),
                'sensor_id':tags['SENSOR_ID'][:120],'calibration_id':tags['CALIBRATION_ID'][:120],'calibrated_at':tags['CALIBRATED_AT'],
                'temperature_kind':'apparent','unit':'Celsius','scale':scale,'offset':offset,'source_crs':src.crs.to_string(),
                'temperature_c':{'min':float(values.min()),'median':float(np.median(values)),'max':float(values.max())},
                'valid_fraction':float(valid.mean()),'threshold_c':threshold,'hot_pixel_count':int(hot.sum()),
                'candidate_area_ha':area,'candidate_geometry':candidate,'coverage':coverage,'input_sha256':digest(path),
                'note':'Apparent radiometric temperature depends on emissivity, atmosphere and reflections. Threshold area is a heat candidate, not a confirmed fire perimeter.'}
