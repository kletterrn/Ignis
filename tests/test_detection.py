import numpy as np
import pytest
from PIL import Image


def region(box=None,score=.9):return {'box':box or [.1,.1,.3,.3],'score':score,'label':'smoke'}


def test_spatial_temporal_gate_rejects_spikes_jumping_boxes_and_gaps():
    pytest.importorskip('cv2')
    from services.camera import TemporalGate
    gate=TemporalGate()
    assert not any(gate.update(t,[region()]) for t in range(4))
    assert gate.update(4,[region()])
    assert not any(gate.update(t,[region()]) for t in range(5,80))
    for t in range(80,110):assert gate.update(t,[]) is None
    assert not any(gate.update(t,[region()]) for t in range(110,114))
    assert gate.update(114,[region()])
    gate=TemporalGate()
    assert not any(gate.update(t,[region([.1,.1,.2,.2] if t%2 else [.8,.8,.9,.9])]) for t in range(12))
    gate=TemporalGate()
    for t in (0,1,2,30,31,32):assert gate.update(t,[region()]) is None
    assert gate.update(33,[region()]) is None
    assert gate.update(34,[region()])


def test_detector_decodes_letterbox_and_rejects_padding_and_bad_outputs():
    pytest.importorskip('cv2')
    from services.camera import SmokeDetector
    detector=SmokeDetector.__new__(SmokeDetector);detector.input='images'
    output=np.zeros((1,5,21504),dtype='float32')
    output[0,:,0]=[512,512,200,100,.9]
    output[0,:,1]=[512,20,200,10,.95]
    class FakeNet:
        def run(self,_,feed):
            tensor=feed['images']
            assert tensor.shape==(1,3,1024,1024)
            assert tensor[0,0,512,512]==1 and tensor[0,1,512,512]==0
            return [output]
    detector.net=FakeNet()
    result=detector.detect(Image.new('RGB',(640,320),'red'))
    assert len(result)==1
    assert result[0]['box']==pytest.approx([.40234375,.40234375,.59765625,.59765625])
    output[0,4,0]=float('nan')
    with pytest.raises(ValueError,match='Unexpected'):detector.detect(Image.new('RGB',(640,320),'red'))


def test_corrupt_detector_is_rejected_before_loading(tmp_path):
    pytest.importorskip('onnxruntime');pytest.importorskip('cv2')
    from services.camera import SmokeDetector
    (tmp_path/'yolov11s-20250722.onnx').write_bytes(b'bad checkpoint')
    with pytest.raises(ValueError,match='checksum'):SmokeDetector(tmp_path)
