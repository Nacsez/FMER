'use strict';
let unitProfiles=null,namedUnitId='',editingUnitId='new';
const namedUnit=()=>unitProfiles?.slots.find(x=>x.id===namedUnitId);
const unitRequest=request=>namedUnit()?{...request,unit_profile:namedUnitId}:request;
const unitContext=()=>namedUnit()?` Profile: ${namedUnit().name}. This name is a local label, not an automatic hardware match. Connect only that instrument before continuing.`:'';
async function fetchUnits(){unitProfiles=await api('/api/units');if(!namedUnit())namedUnitId='';drawUnitSelector();}
function drawUnitSelector(){
 const el=$('#namedUnitSelect');if(!el)return;
 el.innerHTML=option('','No unit profile',namedUnitId)+(unitProfiles?.slots||[]).map(x=>option(x.id,x.name,namedUnitId)).join('');
 el.onchange=run(async()=>{namedUnitId=el.value;invalidateUnit('Check connected unit');unitBackup=null;inspection=null;await useUnitAssignments();notify(namedUnit()?'Using '+namedUnit().name+' setup. Confirm the physical unit before any transfer.':'No named setup selected.');});
}
async function useUnitAssignments(){
 const row=namedUnit();installProfile=row?.default||'';installUserProfile=row?.user||'';
 if(view==='firmware')drawFirmware();
}
async function showUnits(){await Promise.all([fetchUnits(),fetchLoadouts()]);if(view==='units')drawUnits();}
function drawUnits(){
 const row=unitProfiles.slots.find(x=>x.id===editingUnitId)||{id:'new',name:'',notes:'',collection:'',default:'A',user:'A'};
 const choices=selected=>option('','Keep bank unchanged',selected)+profileList().map(p=>option(p.id,p.title,selected)).join('')+(!profileList().some(p=>p.id===selected)&&selected?option(selected,'Missing loadout — choose another',selected):'');
 $('#content').innerHTML=`<div class="bar"><p class="grow">Save a setup for each instrument. Each bank can use a different 64-instrument loadout.</p>${help('units')}</div><section class="panel"><h2>My instruments</h2><div class="bar"><select id="editUnit" aria-label="Unit profile to edit">${option('new','New instrument',row.id)}${unitProfiles.slots.map(x=>option(x.id,x.name,row.id)).join('')}</select><button id="unitProfileRefresh">Refresh</button><button id="unitProfileUndo" ${unitProfiles.can_undo?'':'disabled'}>Undo</button></div><div class="unit-fields"><label>Name<input id="namedUnitName" maxlength="40" value="${esc(row.name)}" placeholder="Malachite"></label><label>Notes<textarea id="namedUnitNotes" maxlength="1000">${esc(row.notes)}</textarea></label><label>Library collection<input id="namedUnitCollection" maxlength="80" value="${esc(row.collection)}" placeholder="Defaults to the instrument name"></label></div><div class="bar"><label>Bank A<select id="namedBankA">${choices(row.default)}</select></label><label>Bank B<select id="namedBankB">${choices(row.user)}</select></label></div><div class="bar"><button id="saveNamedUnit" class="primary">Save setup</button><button id="useNamedUnit" ${row.id==='new'?'disabled':''}>Use this instrument</button><button id="openUnitCollection" ${row.id==='new'?'disabled':''}>Open Library collection</button><button id="removeNamedUnit" class="danger" ${row.id==='new'?'disabled':''}>Delete setup</button></div><p>${unitProfiles.slots.length}/${unitProfiles.capacity} named instruments. Saving or deleting a setup never writes to hardware.</p><p class="muted">Assignments refer to saved loadouts and follow their edits. Save a copy in Instrument loadouts for independent edits per unit. Use the Library collection to organize that instrument’s patches and projects.</p></section><section class="panel"><h2>Connect the intended instrument</h2><p>These names live on this computer. USB names and ports are not unique unit serial numbers. Connect only the unit you intend to manage. Choosing a profile prepares its bank choices and labels operation records; it does not identify hardware or send sounds automatically.</p><div class="bar"><button id="namedUnitTransfers">Manage connected FM-1</button><button id="namedUnitLoadouts">Edit loadouts</button><button id="namedUnitFirmware">Install firmware</button></div></section>`;
 $('#editUnit').onchange=()=>{editingUnitId=$('#editUnit').value;drawUnits();};
 bind('#unitProfileRefresh',showUnits);
 const action=async (action,data={})=>{unitProfiles=await api('/api/units',{action,revision:unitProfiles.revision,...data});if(!namedUnit())namedUnitId='';drawUnitSelector();drawUnits();};
 bind('#saveNamedUnit',async()=>{const profile={id:row.id,name:$('#namedUnitName').value.trim(),notes:$('#namedUnitNotes').value,collection:$('#namedUnitCollection').value.trim()||$('#namedUnitName').value.trim(),default:$('#namedBankA').value,user:$('#namedBankB').value};await action('save',{profile});editingUnitId=row.id==='new'?unitProfiles.slots.at(-1).id:row.id;drawUnits();notify('Instrument setup saved locally.');});
 bind('#unitProfileUndo',()=>action('undo'));
 bind('#useNamedUnit',async()=>{namedUnitId=row.id;drawUnitSelector();invalidateUnit('Check connected unit');unitBackup=null;inspection=null;await useUnitAssignments();notify('Using '+row.name+' setup. Connect only this unit for device operations.');});
 bind('#removeNamedUnit',async()=>{if(await confirmAction('Delete '+row.name+' setup?','Only this local setup is deleted. Loadouts, Library items, backups and the instrument stay unchanged.')){await action('delete',{id:row.id,confirmation:'Delete unit profile'});editingUnitId='new';drawUnits();}});
 bind('#openUnitCollection',()=>{collection=row.collection;query='';trash=false;changeView('library');});
 bind('#namedUnitTransfers',()=>changeView('unit'));bind('#namedUnitLoadouts',()=>changeView('loadouts'));bind('#namedUnitFirmware',()=>changeView('firmware'));
}
