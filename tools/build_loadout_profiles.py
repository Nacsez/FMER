"""Generate included original loadouts; optionally apply the owner's review export."""
import argparse,json
from pathlib import Path
import sound_collections as sounds
import companion_bank as bank
import companion_loadouts as profiles
import sandbox

def build(curation=None):
    rows=sounds.recipes();collections=sounds.collections(rows)
    if curation is not None:collections=sounds.apply_curation(collections,rows,curation)
    template=bank.decode_record(bank.classic_profile(sandbox.find_executable('Release'))[0]['native'])
    entries={r['id']:profiles.sound(sounds.make_entry(r,template),r['title'],(r['description']+' '+r['technique']+' Original FMER; GPL-3.0-only.')[:1000]) for r in rows}
    return dict(format='FMER-INCLUDED-LOADOUTS',version=1,library_version=sounds.VERSION,sounds=entries,
                profiles=[dict(id=p['id'],title=p['title'],description=p['description'],sound_ids=p['patch_ids']) for p in collections])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--curation',type=Path);a=p.parse_args()
    value=build(json.loads(a.curation.read_text()) if a.curation else None)
    (sandbox.ROOT/'host/loadout_profiles.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf8')
    print('Prepared 192 sounds and four 64-instrument profiles')
