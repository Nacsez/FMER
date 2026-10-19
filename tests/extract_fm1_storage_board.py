"""Extract exact storage capture/pause/import board statements; never edit firmware."""
from pathlib import Path
import hashlib,json,sys


def block(source, marker):
    if source.count(marker)!=1:
        raise ValueError('Expected exactly one source marker: '+marker)
    start=source.index(marker);brace=source.index('{',start);depth=1;end=brace+1
    while depth:
        if source[end]=='{':depth+=1
        elif source[end]=='}':depth-=1
        end+=1
    return source[start:end]


def extract(root, out):
    root,out=Path(root),Path(out);out.mkdir(parents=True,exist_ok=True)
    raw=(root/'firmware/fm1/board.c').read_bytes();source=raw.decode().replace('\r\n','\n')
    start=source.index('static fmer_native_state_t native_capture_pending')
    finish=source.index('\nstatic void trace_event(',start)
    helpers='\n'.join(block(source,marker) for marker in (
        'static void mirror_controls(void)', 'static int native_import_conflict(void)',
        'static void native_import_service(void)'))
    pieces={'storage_board_globals.inc':source[start:finish]+'\n'+helpers,
            'storage_board_pause.inc':block(source,'        if(storage_pause_request) {'),
            'storage_board_capture.inc':block(source,'            if(native_capture_request!=native_capture_done) {'),
            'storage_board_import.inc':block(source,'        if(native_import_ready==1u) {')}
    pins={}
    for name,text in pieces.items():
        (out/name).write_text(text+'\n',encoding='utf8')
        pins[name]=hashlib.sha256((text+'\n').encode()).hexdigest()
    report={'board_sha256':hashlib.sha256(raw).hexdigest(),'extractions':pins,
            'scope':'Exact production statements run against real DSP and synthetic board/NOR only'}
    (out/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    extract(sys.argv[1],sys.argv[2])
