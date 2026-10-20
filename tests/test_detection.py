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


def test_confirmation_tolerates_short_misses_but_never_combines_classes():
    pytest.importorskip('cv2')
    from services.camera import TemporalGate
    gate=TemporalGate()
    for t in range(7):assert gate.update(t,[region()] if t in (0,2,3,5) else []) is None
    assert gate.update(7,[region()])
    gate=TemporalGate()
    for t in range(8):
        assert gate.update(t,[{**region(),'label':'fire' if t%2 else 'smoke'}]) is None


def test_slow_samples_can_confirm_but_a_reconnection_resets_history():
    pytest.importorskip('cv2')
    from services.camera import TemporalGate
    gate=TemporalGate()
    for t in (0,3,6,9):assert gate.update(t,[region()]) is None
    assert gate.update(12,[region()])
    gate=TemporalGate()
    for t in (0,1,2,20,21,22,23):assert gate.update(t,[region()]) is None
    assert gate.update(24,[region()])


def test_distinct_episodes_in_one_minute_preserve_both_evidence_items(tmp_path):
    pytest.importorskip('cv2')
    from services.camera import CameraWorker
    from services.store import Store
    root=tmp_path/'sequence';root.mkdir()
    for i in range(40):Image.new('RGB',(48,32)).save(root/f'{i:03}.jpg')
    class Detector:
        name=device='test'
        count=0
        def detect(self,image):
            i=self.count;self.count+=1
            return [region()] if i<5 or i>=35 else []
    store=Store(tmp_path/'state.sqlite');worker=CameraWorker(store,tmp_path/'evidence');worker.classifier=Detector()
    key=worker.start(str(root),'sequence');worker.thread.join(timeout=15)
    assert store.get('jobs',key)['status']=='completed'
    assert sorted(e['offset_seconds'] for e in store.all('evidence'))==[4,39]


def test_video_decode_mismatch_is_visible_in_worker_health(monkeypatch,tmp_path):
    cv2=pytest.importorskip('cv2')
    from services.camera import CameraWorker
    from services.store import Store
    class Capture:
        count=0
        def open(self,*args):return True
        def isOpened(self):return True
        def get(self,key):return 1 if key==cv2.CAP_PROP_FPS else 5
        def read(self):
            self.count+=1
            return (True,np.zeros((32,48,3),dtype='uint8')) if self.count<=2 else (False,None)
        def release(self):pass
    class Detector:
        name=device='test'
        def detect(self,image):return []
    monkeypatch.setattr('services.camera.cv2.VideoCapture',Capture)
    store=Store(tmp_path/'state.sqlite');worker=CameraWorker(store,tmp_path/'evidence');worker.classifier=Detector()
    key=worker.start('input.avi','video');worker.thread.join(timeout=10)
    job=store.get('jobs',key)
    assert job['status']=='completed' and job['frames']==2
    assert job['declared_frames']==5 and job['decoded_frames']==2 and job['decode_warning']


def test_flame_decoder_uses_rgb_and_keeps_classes_separate():
    pytest.importorskip('cv2')
    from services.camera import FlameDetector
    detector=FlameDetector.__new__(FlameDetector);detector.input='images'
    output=np.zeros((1,6,2100),dtype='float32');output[0,:,0]=[160,160,80,80,.6,.1];output[0,:,1]=[160,160,80,80,.1,.9]
    class FakeNet:
        def run(self,_,feed):
            assert feed['images'].shape==(1,3,320,320)
            return [output]
    class Verifier:
        value=.99
        def score(self,image,*,multi_crop):
            assert image.size==(120,120) and multi_crop is False
            return self.value
    detector.verifier=Verifier()
    detector.net=FakeNet();result=detector.detect(Image.new('RGB',(320,320),'red'))
    assert len(result)==1 and result[0]['label']=='fire' and result[0]['score']==pytest.approx(.6)
    assert result[0]['verification_score']==.99
    detector.verifier.value=.3
    assert detector.detect(Image.new('RGB',(320,320),'red'))==[]
