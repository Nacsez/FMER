"""Local Windows PCM capture with per-second receipts; no device firmware writes.

Specify an exact enumerated input name. Eight prequeued buffers keep disk I/O
outside WinMM. A stalled driver fails with the partial WAV and JSON retained.
"""
from __future__ import annotations
import argparse, ctypes as c, hashlib, json, math, struct, time, wave
from pathlib import Path

class Caps(c.Structure):
    _fields_=[('mid',c.c_uint16),('pid',c.c_uint16),('version',c.c_uint32),
              ('name',c.c_wchar*32),('formats',c.c_uint32),('channels',c.c_uint16),('reserved',c.c_uint16)]
class Format(c.Structure):
    _fields_=[('tag',c.c_uint16),('channels',c.c_uint16),('rate',c.c_uint32),
              ('bytes_sec',c.c_uint32),('align',c.c_uint16),('bits',c.c_uint16),('extra',c.c_uint16)]
class Header(c.Structure):
    _fields_=[('data',c.c_void_p),('length',c.c_uint32),('recorded',c.c_uint32),
              ('user',c.c_size_t),('flags',c.c_uint32),('loops',c.c_uint32),('next',c.c_void_p),('reserved',c.c_size_t)]

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device-exact');p.add_argument('--seconds',type=int,default=180);p.add_argument('--output',type=Path)
    a=p.parse_args(argv);mm=c.WinDLL('winmm');devices=[]
    mm.waveInGetDevCapsW.argtypes=[c.c_size_t,c.POINTER(Caps),c.c_uint]
    for i in range(mm.waveInGetNumDevs()):
        cap=Caps();result=mm.waveInGetDevCapsW(i,c.byref(cap),c.sizeof(cap))
        if not result:devices.append(dict(index=i,name=cap.name,channels=cap.channels,formats=cap.formats))
    if not a.device_exact:print(json.dumps(devices,indent=2));return 0
    matching=[d for d in devices if d['name']==a.device_exact]
    if len(matching)!=1 or not a.output or not 1<=a.seconds<=600:raise ValueError('One exact device, output directory and1..600seconds required')
    a.output.mkdir(parents=True,exist_ok=False);report=dict(device=matching[0],seconds_requested=a.seconds,sample_rate=44100,channels=2,bits=16,buffers=[],success=False)
    handle=c.c_void_p();fmt=Format(1,2,44100,176400,4,16,0);headers=[];buffers=[];frames=0;started=last=time.monotonic()
    mm.waveInOpen.argtypes=[c.POINTER(c.c_void_p),c.c_uint,c.POINTER(Format),c.c_size_t,c.c_size_t,c.c_uint]
    for name in ('waveInPrepareHeader','waveInUnprepareHeader','waveInAddBuffer'):
        getattr(mm,name).argtypes=[c.c_void_p,c.POINTER(Header),c.c_uint]
    for name in ('waveInStart','waveInStop','waveInReset','waveInClose'):getattr(mm,name).argtypes=[c.c_void_p]
    def check(result,operation):
        if result:raise RuntimeError(f'{operation}: MMRESULT{result}')
    try:
        check(mm.waveInOpen(c.byref(handle),matching[0]['index'],c.byref(fmt),0,0,0),'waveInOpen')
        for i in range(8):
            buffer=c.create_string_buffer(4096*4);header=Header(c.cast(buffer,c.c_void_p),len(buffer),0,i,0,0,None,0)
            buffers.append(buffer);headers.append(header)
            check(mm.waveInPrepareHeader(handle,c.byref(header),c.sizeof(header)),'prepare')
            check(mm.waveInAddBuffer(handle,c.byref(header),c.sizeof(header)),'queue')
        with wave.open(str(a.output/'capture.wav'),'wb') as wav:
            wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(44100)
            check(mm.waveInStart(handle),'start');started=last=time.monotonic();cursor=0
            while frames<a.seconds*44100:
                header=headers[cursor];now=time.monotonic()
                if header.flags&1:
                    data=buffers[cursor].raw[:header.recorded]
                    if len(data)%4:raise RuntimeError('Driver returned partial stereo PCM frame')
                    wav.writeframesraw(data);samples=struct.unpack('<'+str(len(data)//2)+'h',data)
                    report['buffers'].append(dict(seconds=now-started,frames=len(data)//4,gap_ms=(now-last)*1000,
                        peak=max(map(abs,samples),default=0),rms=math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))))
                    frames+=len(data)//4;last=now
                    check(mm.waveInAddBuffer(handle,c.byref(header),c.sizeof(header)),'requeue');cursor=(cursor+1)%8
                elif now-last>5:raise RuntimeError('No completed audio buffer for five seconds')
                else:time.sleep(.005)
        report['success']=True
    except Exception as error:report['error']=repr(error)
    finally:
        if handle:
            cleanup=[]
            for name in ('waveInStop','waveInReset'):
                result=getattr(mm,name)(handle)
                if result:cleanup.append([name,result])
            for header in headers:
                result=mm.waveInUnprepareHeader(handle,c.byref(header),c.sizeof(header))
                if result:cleanup.append(['unprepare',result])
            result=mm.waveInClose(handle)
            if result:cleanup.append(['close',result])
            if cleanup:report.update(success=False,cleanup_errors=cleanup)
        report.update(frames=frames,elapsed=time.monotonic()-started)
        path=a.output/'capture.wav'
        if path.exists():report['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        (a.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='buffers'}));return 0 if report['success'] else 1

if __name__=='__main__':raise SystemExit(main())
