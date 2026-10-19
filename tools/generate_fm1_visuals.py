"""Deterministically pack the owner's native-size splash and derive DSP routing.
No artistic image edits: RGB565 quantization is the panel's transport format.
"""
from pathlib import Path
import re,json,hashlib
from PIL import Image
R=Path(__file__).resolve().parents[1]
def files():
 p=R/'FMER SPLASH.png';im=Image.open(p).convert('RGB');assert im.size==(240,240)
 rgb=[im.getpixel((x,y)) for y in range(240) for x in range(240)];colors=sorted(set(rgb));assert len(colors)<=4
 palette=[((r>>3)<<11)|((g>>2)<<5)|(b>>3) for r,g,b in colors]
 codes=[colors.index(x) for x in rgb];data=[sum(codes[i+j]<<(6-2*j) for j in range(4)) for i in range(0,len(codes),4)]
 splash='/* Generated from owner FMER SPLASH.png; see tools/generate_fm1_visuals.py. */\n#ifndef FMER_SPLASH_H\n#define FMER_SPLASH_H\n#include <stdint.h>\nstatic const uint16_t fmer_splash_palette[4]={'+','.join(hex(x) for x in palette+[0]*(4-len(palette)))+'};\nstatic const uint8_t fmer_splash_pixels[14400]={\n'+''.join(' '+','.join(str(v) for v in data[i:i+30])+',\n' for i in range(0,len(data),30))+'};\n#endif\n'
 src=R/'third_party/msfa/src/fm_core.cc';text=src.read_text(encoding='utf8');body=text.split('const FmAlgorithm algorithms[32] = {',1)[1].split('\n};',1)[0]
 flags=[[int(x,16) for x in re.findall(r'0x[0-9a-f]+',line)] for line in body.splitlines() if '0x' in line];assert len(flags)==32 and all(len(x)==6 for x in flags)
 rows=[]
 for num,ops in enumerate(flags):
  buses=[0,0,0];incoming=[];feedback=0;unsupported=0
  for i,f in enumerate(ops):
   source=(f>>4)&3;dest=f&3;incoming.append(buses[source] if source else 0)
   if f&0xc0==0xc0 and not source:feedback|=1<<i
   elif f&0xc0:unsupported=1
   buses[dest]=(buses[dest] if f&4 else 0)|(1<<i)
  carriers=buses[0];rank=[0]*6
  for i in reversed(range(6)):
   children=[j for j in range(i+1,6) if incoming[j]&(1<<i)]
   rank[i]=1+max(rank[j] for j in children) if children else 0
  # Connected components occupy fixed horizontal territories; each level is
  # evenly spaced. Shared branches are represented by their actual edges.
  groups=[];unseen=set(range(6))
  while unseen:
   group={min(unseen)}
   while True:
    nxt=group|{j for i in group for j in range(6) if incoming[i]&(1<<j) or incoming[j]&(1<<i)}
    if nxt==group:break
    group=nxt
   groups.append(sorted(group));unseen-=group
  xs=[0]*6
  for gi,g in enumerate(groups):
   left=12+gi*216//len(groups);width=216//len(groups)
   for level in set(rank[i] for i in g):
    nodes=[i for i in g if rank[i]==level]
    for k,i in enumerate(nodes):xs[i]=left+(k+1)*width//(len(nodes)+1)
  ys=[139-24*r for r in rank]
  rows.append(dict(algorithm=num,incoming=incoming,carriers=carriers,feedback=feedback,unsupported_feedback=unsupported,x=xs,y=ys))
 header='/* Generated from the pinned MSFA routing table (Apache-2.0 data); FMER layout. */\n#ifndef FMER_ALGORITHM_DIAGRAMS_H\n#define FMER_ALGORITHM_DIAGRAMS_H\n#include <stdint.h>\ntypedef struct {uint8_t incoming[6],carriers,feedback,unsupported_feedback,x[6],y[6];} fmer_algorithm_diagram_t;\nstatic const fmer_algorithm_diagram_t fmer_algorithm_diagrams[32]={\n'
 for r in rows:header+=' {{'+','.join(map(str,r['incoming']))+'},'+','.join(str(r[k]) for k in ('carriers','feedback','unsupported_feedback'))+',{'+','.join(map(str,r['x']))+'},{'+','.join(map(str,r['y']))+'}},\n'
 header+='};\n#endif\n'
 manifest=dict(schema=1,splash_source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),routing_source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),scope='Graph shows actual MSFA feedforward/self-feedback. Multi-operator feedback in algorithms4/6 is unimplemented upstream and explicitly marked unavailable.',algorithms=rows)
 return {R/'firmware/fm1/splash.h':splash,R/'firmware/fm1/algorithm_diagrams.h':header,R/'host/fm_algorithms.json':json.dumps(manifest,indent=2)+'\n'}
if __name__=='__main__':
 import sys
 check='--check' in sys.argv
 for p,data in files().items():
  if check:assert p.read_text(encoding='utf8')==data,p
  else:p.write_text(data,encoding='utf8')
 print('Visual assets verified' if check else 'Visual assets generated')
