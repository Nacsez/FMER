"""Offline ELF32 runtime comparison with relocation targets; never device I/O.

Equal unrelocated code is insufficient: relocation targets and public symbol
definitions must also agree. Different objects require behavioral qualification.
"""
from pathlib import Path
import argparse,hashlib,json,re,struct
import source_runtime

def object_contract(raw):
    if len(raw)<52 or raw[:7]!=b'\x7fELF\x01\x01\x01':raise ValueError('Expected ELF32 little endian')
    off=struct.unpack_from('<I',raw,32)[0];size,n,strings=struct.unpack_from('<HHH',raw,46)
    if size!=40 or not 0<strings<n or off+n*size>len(raw):raise ValueError('Invalid ELF section table')
    sections=[struct.unpack_from('<10I',raw,off+i*size) for i in range(n)]
    def payload(s):
        if s[1]==8:return b''
        if s[4]+s[5]>len(raw):raise ValueError('ELF section outside file')
        return raw[s[4]:s[4]+s[5]]
    def word(table,i):
        if i>=len(table):raise ValueError('ELF string outside table')
        end=table.find(b'\0',i)
        if end<0:raise ValueError('Unterminated ELF string')
        return table[i:end].decode('utf8')
    names=[word(payload(sections[strings]),s[0]) for s in sections]
    allocated={names[i]:dict(type=s[1],flags=s[2],size=s[5],data=payload(s).hex())
               for i,s in enumerate(sections) if s[2]&2 and s[5]}
    def symbols(index):
        table=sections[index];data=payload(table);strings_data=payload(sections[table[6]])
        if table[9]!=16 or len(data)%16:raise ValueError('Invalid ELF symbols')
        rows=[]
        for pos in range(0,len(data),16):
            name,value,size,info,other,sh=struct.unpack_from('<IIIBBH',data,pos)
            section=names[sh] if sh<len(names) else str(sh)
            rows.append(dict(name=word(strings_data,name),value=value,size=size,bind=info>>4,type=info&15,section=section,visibility=other))
        return rows
    relocations=[];exports=[]
    for i,s in enumerate(sections):
        if s[1]==2:
            exports.extend(x for x in symbols(i) if x['bind'] and x['section'] in allocated)
        if s[1] not in (4,9) or not s[7]<n or names[s[7]] not in allocated:continue
        data=payload(s);width=12 if s[1]==4 else 8;syms=symbols(s[6])
        if len(data)%width or s[9]!=width:raise ValueError('Invalid ELF relocations')
        for pos in range(0,len(data),width):
            address,info=struct.unpack_from('<II',data,pos);symbol=syms[info>>8]
            # Local names can be assembler-generated. Their section/value/type
            # identify the target; undefined/global symbol names remain material.
            target={k:v for k,v in symbol.items() if k!='size' and (k!='name' or symbol['bind'] or symbol['section']=='')}
            relocations.append(dict(section=names[s[7]],offset=address,type=info&255,target=target,
                                    addend=struct.unpack_from('<i',data,pos+8)[0] if width==12 else None))
    return dict(allocated=allocated,relocations=relocations,exports=sorted(exports,key=lambda x:x['name']))

def audit(reference,candidate,reference_objects):
    a=json.loads((reference/'report.json').read_text());b=json.loads((candidate/'report.json').read_text())
    if not a['success'] or not b['success'] or b.get('runtime',{}).get('vendor_binary_archives') is not False:
        raise ValueError('Expected a successful source-runtime candidate')
    for folder,report in ((reference,a),(candidate,b)):
        if source_runtime.digest(folder/'fm1.elf')!=report['elf']['sha256']:raise ValueError('ELF hash differs')
        for item in report['objects']:
            if source_runtime.digest(folder/item['path'])!=item['sha256']:raise ValueError('Application object changed')
    if a['objects']!=b['objects']:raise ValueError('Application code changed in runtime-only comparison')
    units=source_runtime.verify()['units'];rows=[]
    for u in units:
        old=reference_objects/u['archive']/u['member'];new=candidate/'runtime/objects'/u['archive']/u['member']
        current=object_contract(new.read_bytes())
        row=dict(archive=u['archive'],member=u['member'],source=u['source'],new_sha256=source_runtime.digest(new))
        if old.exists():
            original=object_contract(old.read_bytes())
            row.update(reference_sha256=source_runtime.digest(old),allocated_equal=original['allocated']==current['allocated'],
                       relocations_equal=original['relocations']==current['relocations'],exports_equal=original['exports']==current['exports'])
            row['object_contract_equal']=all(row[k] for k in ('allocated_equal','relocations_equal','exports_equal'))
        else:row['reference_separate_object']=False
        rows.append(row)
    link=json.loads((candidate/'link.json').read_text())['command']
    maptext=(candidate/'fm1.map').read_text()
    if any('pi32v2-lib' in x for x in link) or 'pi32v2-lib' in maptext:
        raise ValueError('Vendor runtime archive leaked into link')
    before={x['name']:x['size'] for x in a['elf']['sections']};after={x['name']:x['size'] for x in b['elf']['sections']}
    return dict(schema=1,application_objects_identical=len(a['objects']),reference_elf=a['elf']['sha256'],candidate_elf=b['elf']['sha256'],
                vendor_archive_link=False,source_manifest_sha256=source_runtime.digest(source_runtime.SOURCE/'PROVENANCE.json'),
                section_deltas={k:after[k]-before[k] for k in after},objects=rows,
                exact_object_contracts=sum(x.get('object_contract_equal',False) for x in rows),
                scope='Offline source/link/object evidence; not whole-firmware or mathematical equivalence, audio or target timing qualification')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('reference','candidate','reference-objects','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();report=audit(a.reference,a.candidate,a.reference_objects)
    a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='objects'}))
if __name__=='__main__':main()
