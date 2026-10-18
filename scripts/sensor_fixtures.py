"""Reproducible synthetic sensor fixtures; these are not field validation data."""
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from PIL import Image,ImageFilter


def create(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(71)
    left=np.asarray(Image.fromarray(rng.integers(0,256,(192,320),dtype='uint8')).filter(ImageFilter.GaussianBlur(.6)))
    right=rng.integers(0,256,left.shape,dtype='uint8');right[:,:-12]=left[:,12:]
    Image.fromarray(left).save(root/'left.png');Image.fromarray(right).save(root/'right.png')
    calibration={'calibration_id':'SYNTHETIC-FIXTURE-NOT-A-REAL-RIG','calibrated_at':'2026-01-01T00:00:00Z',
                 'translation_unit':'m','rms_px':0,'image_size':[320,192],
                 'K1':[[240,0,160],[0,240,96],[0,0,1]],'K2':[[240,0,160],[0,240,96],[0,0,1]],
                 'D1':[0,0,0,0,0],'D2':[0,0,0,0,0],'R':[[1,0,0],[0,1,0],[0,0,1]],'T':[-.2,0,0]}
    (root/'calibration.json').write_text(json.dumps(calibration,indent=2),encoding='utf-8')
    thermal=np.full((32,32),29315,dtype='uint16');thermal[8:24,8:24]=35315;thermal[0,:]=0
    with rasterio.open(root/'thermal.tif','w',driver='GTiff',height=32,width=32,count=1,dtype='uint16',
                       crs='EPSG:3035',transform=from_origin(4321000,3210000,2,2),nodata=0) as dst:
        dst.write(thermal,1);dst.scales=(.01,);dst.offsets=(0,)
        dst.update_tags(TEMPERATURE_UNIT='Kelvin',TEMPERATURE_KIND='apparent',SENSOR_ID='SYNTHETIC',
                        CALIBRATION_ID='SYNTHETIC-ONLY',CALIBRATED_AT='2026-01-01T00:00:00Z',ACQUIRED_AT='2026-10-18T00:00:00Z')
    return calibration


if __name__=='__main__':
    create(Path(__file__).resolve().parents[1]/'data'/'sensor-fixtures')
    print('Synthetic sensor fixtures: data/sensor-fixtures; stereo expected depth 4 m; thermal 20/80 C')
