"""Named local instrument setups; names are not hardware identities.

Loadout references intentionally follow edits to those saved loadouts. Copy a
loadout for independent per-unit editing. No MIDI enumeration or I/O on import.
"""
from copy import deepcopy
import uuid
import library
from companion_shelf import text

CAPACITY=16

class Units(library.PatchLibrary):
    def __init__(self,root,executable,loadouts):
        super().__init__(root,executable);self.loadouts=loadouts

    def _empty(self):return dict(format='FMER-UNITS',version=1,capacity=CAPACITY,revision=0,slots=[],undo_slots=None)

    def _validate_state(self,state):
        if not isinstance(state,dict) or set(state)!=set(self._empty()) or state['format']!='FMER-UNITS' or state['version']!=1 or state['capacity']!=CAPACITY:raise ValueError('Unsupported unit profiles')
        library.integer(state['revision'],0,2**53-1,'revision')
        for key in ('slots','undo_slots'):
            rows=state[key]
            if key=='undo_slots' and rows is None:continue
            if not isinstance(rows,list) or len(rows)>CAPACITY:raise ValueError('Up to16 named instruments can be saved')
            for row in rows:
                if set(row)!={'id','name','notes','collection','default','user'}:raise ValueError('Incomplete unit profile')
                if str(uuid.UUID(row['id']))!=row['id']:raise ValueError('Invalid unit profile identity')
                text(row['name'],40,'Unit name');text(row['notes'],1000,'Notes',True);text(row['collection'],80,'Library collection')
                for bank in ('default','user'):text(row[bank],80,'Loadout reference',True)
            if len({r['id'] for r in rows})!=len(rows) or len({r['name'].casefold() for r in rows})!=len(rows):raise ValueError('Each unit needs a unique name')

    def get(self,identifier):
        row=next((x for x in self._read()['slots'] if x['id']==identifier),None)
        if row is None:raise ValueError('Unit profile missing; refresh before continuing')
        return deepcopy(row)

    def assignments(self,identifier):
        row=self.get(identifier)
        return {k:self.loadouts.dispatch(dict(action='export',id=row[k])) if row[k] else None for k in ('default','user')}

    def dispatch(self,request):
        library.fields(request,{'action','revision','profile','id','confirmation'},'unit profile request')
        action=request.get('action')
        if action=='assignments':return self.assignments(request.get('id'))
        library.choice(action,{'save','delete','undo'},'unit profile action')
        def change(state):
            rows=deepcopy(state['slots'])
            if action=='undo':
                if state['undo_slots'] is None:raise ValueError('Nothing to undo')
                return deepcopy(state['undo_slots'])
            if action=='delete':
                if request.get('confirmation')!='Delete unit profile':raise ValueError('Confirm deleting the local unit profile')
                if not any(x['id']==request.get('id') for x in rows):raise ValueError('Unit profile missing')
                return [x for x in rows if x['id']!=request['id']]
            row=deepcopy(request.get('profile'))
            if not isinstance(row,dict):raise ValueError('Missing unit profile')
            for key in ('default','user'):
                if row.get(key):self.loadouts.get(row[key])
            if row.get('id')=='new':row['id']=str(uuid.uuid4());rows.append(row)
            else:
                index=next((i for i,x in enumerate(rows) if x['id']==row.get('id')),None)
                if index is None:raise ValueError('Unit profile missing; refresh before saving')
                rows[index]=row
            return rows
        self._mutate(request.get('revision'),action,change)
        return self.snapshot()
