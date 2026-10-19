"""Portable, versioned PC catalog. No device I/O; reuse durable library transactions.

Projects may carry explicit snapshots of their referenced sounds. Collections
are metadata, never filesystem paths. Trash and one transaction Undo are local.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import uuid
import companion_bank as bank
import library

FORMAT = 'FMER-CATALOG'
CAPACITY = 512


def text(value, maximum, label, empty=False):
    if not isinstance(value, str) or len(value) > maximum or (not empty and not value.strip()) or any(ord(c) < 32 for c in value):
        raise ValueError(f'{label}: use {1 if not empty else 0}..{maximum} printable characters')
    return value.strip()


def envelope(payload):
    return dict(format='FMER-CATALOG-FILE', version=1, payload=payload,
                sha256=hashlib.sha256(library.canonical(payload)).hexdigest())


class Catalog(library.PatchLibrary):
    def _empty(self):
        return dict(format=FORMAT, version=1, capacity=CAPACITY, revision=0, slots=[], undo_slots=None)

    _envelope = staticmethod(envelope)

    @staticmethod
    def validate_item(item):
        keys={'id','kind','title','collection','tags','notes','favorite','entry','dependencies','created','updated','trashed'}
        if not isinstance(item,dict) or set(item)!=keys:raise ValueError('Incomplete catalog item')
        if str(uuid.UUID(item['id']))!=item['id']:raise ValueError('Invalid catalog identity')
        library.choice(item['kind'],{'instrument','project'},'item type')
        text(item['title'],80,'Title');text(item['collection'],80,'Collection',True);text(item['notes'],1000,'Notes',True)
        for field in ('favorite','trashed'):library.boolean(item[field],field)
        for field in ('created','updated'):datetime.fromisoformat(item[field])
        if not isinstance(item['tags'],list) or len(item['tags'])>12 or len(set(item['tags']))!=len(item['tags']):raise ValueError('Use up to12 distinct tags')
        for tag in item['tags']:text(tag,24,'Tag')
        bank.BankLibrary.validate_entry(item['entry'])
        dependencies=item['dependencies']
        if not isinstance(dependencies,dict) or len(dependencies)>4:raise ValueError('A project has at most four referenced sounds')
        if item['kind']=='instrument' and dependencies:raise ValueError('Instrument cannot contain project dependencies')
        refs={str(t['sound_ref']) for t in bank.decode_record(item['entry']['native'])['tracks']}
        for slot,entry in dependencies.items():
            if slot not in refs:raise ValueError('Dependency does not match a project track reference')
            bank.BankLibrary.validate_entry(entry)

    def _validate_state(self,state):
        if not isinstance(state,dict) or set(state)!=set(self._empty()):raise ValueError('Invalid catalog fields')
        if state['format']!=FORMAT or type(state['version']) is not int or state['version']!=1 or state['capacity']!=CAPACITY:raise ValueError('Unsupported catalog format')
        library.integer(state['revision'],0,2**53-1,'revision')
        for field in ('slots','undo_slots'):
            items=state[field]
            if items is None and field=='undo_slots':continue
            if not isinstance(items,list) or len(items)>CAPACITY:raise ValueError('Catalog capacity512 reached; export before clearing Trash')
            for item in items:self.validate_item(item)
            if len({i['id'] for i in items})!=len(items):raise ValueError('Duplicate catalog identity')

    def _unpack(self,value):
        if not isinstance(value,dict) or set(value)!={'format','version','payload','sha256'} or value['format']!='FMER-CATALOG-FILE' or type(value['version']) is not int or value['version']!=1:raise ValueError('Not an FMER catalog file')
        encoded=library.canonical(value['payload'])
        if len(encoded)>library.MAX_FILE_BYTES or hashlib.sha256(encoded).hexdigest()!=value['sha256']:raise ValueError('Catalog checksum or size mismatch')
        self._validate_state(value['payload']);return deepcopy(value['payload'])

    def dispatch(self,request):
        library.fields(request,{'action','revision','id','ids','kind','title','collection','tags','notes','favorite','entry','dependencies','backup','confirmation'},'catalog request')
        action=request.get('action')
        if action=='snapshot':return self.snapshot()
        if action=='backup':return dict(backup=envelope(self._read()))
        if action=='export':
            state=self._read();wanted=request.get('ids')
            if not isinstance(wanted,list) or not wanted:raise ValueError('Select items to export')
            items=[i for i in state['slots'] if i['id'] in wanted]
            if len(items)!=len(set(wanted)):raise ValueError('Export item missing')
            return dict(backup=envelope({**state,'slots':items,'undo_slots':None}))
        library.choice(action,{'add','update','duplicate','move','trash','recover','purge','undo','import','restore','extract'},'catalog action')
        if action in ('purge','restore') and request.get('confirmation')!=('Empty Catalog Trash' if action=='purge' else 'Replace Local Catalog'):raise ValueError('Confirm the named catalog action')
        def change(state):
            items=deepcopy(state['slots']);now=datetime.now(timezone.utc).isoformat()
            if action=='undo':
                if state['undo_slots'] is None:raise ValueError('Nothing to undo')
                return deepcopy(state['undo_slots'])
            if action in ('import','restore'):
                imported=self._unpack(request.get('backup'))['slots']
                if action=='restore':return imported
                for item in imported:item['id']=str(uuid.uuid4());item['created']=item['updated']=now
                return items+imported
            if action=='add':
                item=dict(id=str(uuid.uuid4()),kind=request.get('kind'),title=request.get('title'),collection=request.get('collection',''),tags=request.get('tags',[]),notes=request.get('notes',''),favorite=request.get('favorite',False),entry=deepcopy(request.get('entry')),dependencies=deepcopy(request.get('dependencies',{})),created=now,updated=now,trashed=False)
                self.validate_item(item);return items+[item]
            if action=='purge':return [i for i in items if not i['trashed']]
            ids=request.get('ids',[request.get('id')])
            if not isinstance(ids,list) or not ids or len(set(ids))!=len(ids):raise ValueError('Select distinct catalog items')
            selected=[i for i in items if i['id'] in ids]
            if len(selected)!=len(ids):raise ValueError('Selected item is missing; refresh the catalog')
            for item in selected:
                if action=='extract':
                    if item['kind']!='project' or not item['dependencies']:raise ValueError('No embedded project instruments')
                    for slot,entry in item['dependencies'].items():
                        items.append(dict(id=str(uuid.uuid4()),kind='instrument',title=entry['name'],collection=item['collection'],tags=[],notes='Extracted from '+item['title']+'; unit slot reference '+slot,favorite=False,entry=deepcopy(entry),dependencies={},created=now,updated=now,trashed=False))
                elif action=='duplicate':
                    copied=deepcopy(item);copied.update(id=str(uuid.uuid4()),created=now,updated=now,title=(item['title']+' copy')[:80],trashed=False);items.append(copied)
                elif action=='move':item['collection']=text(request.get('collection'),80,'Collection',True)
                elif action in ('trash','recover'):item['trashed']=action=='trash'
                elif action=='update':
                    for key in ('title','collection','tags','notes','favorite','entry','dependencies'):
                        if key in request:item[key]=deepcopy(request[key])
                if action not in ('extract','duplicate'):item['updated']=now
            return items
        return self._mutate(request.get('revision'),action,change)
