"""Original Expressions 2 revisions guided by the owner's Expressions 1 survey.
No OEM parameters or audio are inputs. Stable IDs allow review comparison.
"""
from copy import deepcopy
CARRIERS=(0x28,0x28,0x24,0x24,0x2a,0x2a,0x28,0x28,0x28,0x24,0x24,0x28,0x28,0x28,0x28,0x20,0x20,0x20,0x26,0x34,0x36,0x2e,0x36,0x3e,0x3e,0x34,0x34,0x29,0x3a,0x39,0x3e,0x3f)
CHANGES={
 'fm_marrow':'Raised carrier body for a more audible, punchy kick.',
 'fm_subdrop':'Raised the sub body and softened upper modulation for a rounder drop.',
 'fm_industryk':'Harder transient, brighter feedback grit and restrained drive.',
 'fm_chinatrash':'More inharmonic edge and feedback grit with a shorter tail.',
 'fm_fretless':'Enabled subtle delayed pitch and amplitude movement on held notes.',
 'fm_squishlow':'Stronger upper-key carrier damping to balance the register.',
 'fm_steelpan':'Added a lightly inharmonic modulator and brighter metallic transient.',
 'fm_kalimba':'Reduced metallic modulation; retained a rounded woody pluck.',
 'fm_harpdew':'Changed upper partial ratios and staggered decays for a distinct pluck.',
 'fm_mutehorn':'Reduced lower carrier body and raised the upper nasal component.',
 'fm_panbreath':'Stronger delayed vibrato and a shorter breath transient.',
 'fm_jazzflute':'Reduced noisy feedback and inharmonic modulation buzz.',
 'fm_clarivox':'Strengthened even-ratio modulation for an odd-harmonic reed tone.',
 'fm_oboeedge':'Narrower bright reed attack with a more focused held spectrum.',
 'fm_harmonica':'Unequal reed decays, slight detune and delayed vibrato.',
 'fm_digibrass':'Sharper modulator attack and falling brightness for brass bite.',
 'fm_plastik':'Reduced harsh sustained modulation while preserving the attack.',
 'fm_zigzag':'Added contrasting fixed-frequency sparkle and rhythmic tremolo.',
 'fm_bowedroom':'Softer carrier onset and more upper-partial motion; less horn body.',
 'fm_silkstrng':'More upper partials and gentle pitch motion for air.',
 'fm_harmonium':'Rebalanced organ-like partials with restrained reed modulation.',
 'fm_analogmist':'Brighter modulation and slow amplitude movement.',
 'va_trash_cym':'Reduced sustain and shortened decay/release for less wash.',
 'va_folded_edge':'Reduced sustain, resonance and drive for a less dominant level.',
 'va_soft_fire':'Enabled subtle pitch motion and stronger slow chorus.',
}
def revise(rows):
 rows=deepcopy(rows)
 for r in rows:
  key=r['id']
  if key not in CHANGES:continue
  c=r['controls']
  if key.startswith('fm_'):
   p=r['vced'];mask=CARRIERS[p[134]];car=[i for i in range(6) if mask>>i&1];mod=[i for i in range(6) if not mask>>i&1]
   def levels(ops,delta):
    for i in ops:p[21*i+16]=max(0,min(99,p[21*i+16]+delta))
   def lfo(rate,delay,pitch,amp):p[137:141]=[rate,delay,pitch,amp];c[147]=1
   if key=='fm_marrow':levels(car,4)
   elif key=='fm_subdrop':levels(car,4);levels(mod,-7)
   elif key=='fm_industryk':p[135]=7;levels(mod,4);c[168]=12
   elif key=='fm_chinatrash':p[135]=7;levels(mod,3);p[19]=73;c[168]=8
   elif key=='fm_fretless':lfo(31,38,3,16)
   elif key=='fm_squishlow':
    for i in car:p[21*i+8]=42;p[21*i+10]=28;p[21*i+12]=1
   elif key=='fm_steelpan':levels(mod,5);p[21*mod[0]+19]=19
   elif key=='fm_kalimba':levels(mod,-9);p[135]=min(2,p[135])
   elif key=='fm_harpdew':
    for n,i in enumerate(mod):p[21*i+18]=[3,7,11][n%3];p[21*i+1]=62+n*4
   elif key=='fm_mutehorn':levels(car,-4);levels(mod,5)
   elif key=='fm_panbreath':lfo(31,32,5,2);p[1]=min(99,p[1]+10)
   elif key=='fm_jazzflute':p[135]=3;levels(mod,-8)
   elif key=='fm_clarivox':
    for i in mod:p[21*i+17:21*i+20]=[0,2,0]
    levels(mod,4);p[135]=1
   elif key=='fm_oboeedge':levels(mod,5);p[135]=3;lfo(31,50,3,1)
   elif key=='fm_harmonica':
    for n,i in enumerate(car):p[21*i+20]=5+n*2;p[21*i+1]=48+n*5
    lfo(30,45,4,3)
   elif key=='fm_digibrass':
    for i in mod:p[21*i]=97;p[21*i+1]=65;p[21*i+5]=86
    levels(mod,6)
   elif key=='fm_plastik':levels(mod,-6);p[135]=max(0,p[135]-2)
   elif key=='fm_zigzag':p[21*mod[0]+17:21*mod[0]+20]=[1,2,35];lfo(25,0,1,23)
   elif key=='fm_bowedroom':
    levels(car,-3);levels(mod,3)
    for i in car:p[21*i]=68
    lfo(28,32,3,3)
   elif key=='fm_silkstrng':levels(mod,5);lfo(30,45,3,2)
   elif key=='fm_harmonium':
    p[135]=1;levels(mod,-8)
    for n,i in enumerate(car):p[21*i+18]=[1,2,4,3][n%4];p[21*i+6]=96
    lfo(24,50,2,3)
   elif key=='fm_analogmist':levels(mod,5);lfo(20,15,2,12)
  elif key=='va_trash_cym':c[165]=min(c[165],420);c[166]=min(c[166],12);c[167]=min(c[167],160);c[168]=min(c[168],8)
  elif key=='va_folded_edge':c[166]=max(15,c[166]-18);c[163]=max(0,c[163]-12);c[168]=max(0,c[168]-12)
  elif key=='va_soft_fire':c[147]=1;c[175]=130;c[176]=8;c[169]=32;r['modulation_profiles']=[0,0]
  r['technique']+=' Expressions 2: '+CHANGES[key]
 return rows
