"""Opt-in, bounded diagnostic summary. Never exports banks, ROMs or raw MIDI."""
import json,re
from pathlib import Path
FIELDS=('id','action','state','created','finished','message','error','identity')
def summary(root):
    records=[]
    paths=sorted(Path(root).glob('*/job.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:30]
    for path in paths:
        if path.is_symlink() or path.stat().st_size>8*1024*1024:continue
        try:item=json.loads(path.read_text(encoding='utf8'))
        except (OSError,ValueError):continue
        out={k:item[k] for k in FIELDS if isinstance(item.get(k),(str,int,bool))}
        for k,v in out.items():
            if isinstance(v,str):out[k]=re.sub(r'(?:[A-Za-z]:[\\/]|/Users/|/home/)[^\r\n\"<>]*','[local path removed]',v)[:2000]
        records.append(out)
    return dict(format='FMER-BETA-FEEDBACK',version=1,companion='734',firmware='734',operations=records,
        privacy='No patches, projects, ROMs, raw MIDI, device metadata pages or automatic uploads. Review your written feedback before sharing.')
