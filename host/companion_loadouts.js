'use strict';
let loadouts=null,loadoutId='A',loadoutSlot=0,installProfile='',installUserProfile='';
const profileList=()=>[...(loadouts?.included||[]),...(loadouts?.slots||[])];
const currentProfile=()=>profileList().find(p=>p.id===loadoutId)||profileList()[0];
const slotSound=(entry,title,notes='')=>({entry:structuredClone(entry),title:title||entry.name,notes});
async function fetchLoadouts(){loadouts=await api('/api/loadouts');}
async function showLoadouts(){await fetchLoadouts();if(view==='loadouts')drawLoadouts();}
async function loadoutAction(action,data={}){
 notify('Saving profile?');
 try{loadouts=await api('/api/loadouts',{action,revision:loadouts.revision,...data});}
 catch(e){await fetchLoadouts();drawLoadouts();throw e;}
 if(!profileList().some(p=>p.id===loadoutId))loadoutId=profileList()[0].id;
 drawLoadouts();notify('Profile saved on this computer. Instrument unchanged.');
}
async function copyProfile(){
 await loadoutAction('copy',{id:currentProfile().id,title:$('#profileTitle').value.trim()||currentProfile().title+' copy'});
 loadoutId=loadouts.slots.at(-1).id;drawLoadouts();
}
async function saveProfile(profile){await loadoutAction('save',{profile});}
async function profileFromBank(){
 banks=await api('/api/banks');const start=Number($('#profileBankSource').value),entries=banks.slots.slice(start,start+64);
 if(entries.some(e=>!e))throw Error('This PC bank has empty slots. Fill them before saving a complete loadout.');
 const profile={id:'new',title:start?'My Bank B loadout':'My Bank A loadout',description:'Snapshot of PC sound bank; changes to that bank do not alter this profile.',slots:entries.map(e=>slotSound(e))};
 await saveProfile(profile);loadoutId=loadouts.slots.at(-1).id;drawLoadouts();
}
function drawLoadouts(){
 $('#profileAudio')?.pause();
 const p=currentProfile(),editable=loadouts.slots.some(x=>x.id===p.id),chosen=p.slots[loadoutSlot];loadoutId=p.id;
 $('#content').innerHTML=`<div class="bar"><p class="grow">A loadout is 64 instruments in a fixed order. Save it once, use it during installation or send it to an existing FMER.</p>${help('loadouts')}</div>
 <section class="panel"><div class="bar"><label class="grow">Loadout <select id="profileSelect">${profileList().map(x=>option(x.id,(loadouts.included.some(i=>i.id===x.id)?'Included · ':'My profiles · ')+x.title,p.id)).join('')}</select></label><button id="profileRefresh">Refresh</button><button id="profileImport">Import profile</button><button id="profileExport">Export profile</button></div>
 <div class="bar"><label class="grow">Name <input id="profileTitle" maxlength="80" value="${esc(p.title)}"></label><button id="profileCopy">Save a copy</button><button id="profileSave" ${editable?'':'disabled'}>Save name &amp; notes</button></div><label>Notes <textarea id="profileDescription" maxlength="1000" rows="2" ${editable?'':'disabled'}>${esc(p.description)}</textarea></label>
 <p class="muted">${editable?'Independent saved snapshot. Each change supports Undo.':'Included profile: save a copy to customize. A–D are the current Expressions selections; Classic retains the previous firmware sounds.'} ${loadouts.slots.length}/${loadouts.capacity} personal profiles.</p>
 <div class="bar"><button id="profileUndo" ${loadouts.can_undo?'':'disabled'}>Undo profile change</button><button id="profileDelete" class="danger" ${editable?'':'disabled'}>Delete profile</button><select id="profileBankSource" aria-label="PC bank to capture">${option(0,'PC Bank A',0)}${option(64,'PC Bank B',0)}</select><button id="profileFromBank">Save bank as profile</button></div></section>
 <section class="panel"><h2>Instrument order</h2><p>Slot numbers match the instrument’s 00–63 display. Select a slot to replace or move it. Library edits do not change saved profiles.</p>
 <div class="loadout-grid" role="group" aria-label="64 loadout slots">${p.slots.map((s,i)=>`<button data-loadout-slot="${i}" aria-pressed="${i===loadoutSlot}" class="${i===loadoutSlot?'active':''}"><small>${String(i).padStart(2,'0')}</small><strong>${esc(s.entry.name)}</strong><span>${esc(s.entry.category)}</span></button>`).join('')}</div>
 <div class="bar"><strong>Slot ${String(loadoutSlot).padStart(2,'0')} · ${esc(chosen.title)}</strong><button id="profileAudition">Listen</button><audio id="profileAudio" controls preload="none"></audio><button id="profileReplace" ${editable?'':'disabled'}>Choose instrument…</button></div>
 <div class="bar"><button id="profileUp" ${editable&&loadoutSlot>0?'':'disabled'}>Move earlier</button><button id="profileDown" ${editable&&loadoutSlot<63?'':'disabled'}>Move later</button><label>Move to <select id="profileMoveTarget">${p.slots.map((s,i)=>option(i,String(i).padStart(2,'0')+' · '+s.entry.name,loadoutSlot)).join('')}</select></label><button id="profileMove" ${editable?'':'disabled'}>Move</button></div><p class="muted">${esc(chosen.notes)}</p></section>
 <section class="panel"><h2>Use this loadout</h2><p>Replacing slots changes the sounds used by projects that reference them. Projects are preserved; their references are not remapped. Firmware reset actions still restore the compiled defaults (Spectrum on 735; Classic on 734).</p><div class="bar"><button id="profileForDefault">Choose for Bank A</button><button id="profileForUser">Choose for Bank B</button><button id="profileUseInstall">Use when installing firmware</button></div></section>`;
 $('#profileSelect').onchange=()=>{loadoutId=$('#profileSelect').value;loadoutSlot=0;drawLoadouts();};
 document.querySelectorAll('[data-loadout-slot]').forEach(b=>b.onclick=()=>{loadoutSlot=Number(b.dataset.loadoutSlot);drawLoadouts();});
 bind('#profileRefresh',showLoadouts);bind('#profileCopy',copyProfile);
 bind('#profileSave',()=>saveProfile({...structuredClone(p),title:$('#profileTitle').value.trim(),description:$('#profileDescription').value}));
 bind('#profileUndo',()=>loadoutAction('undo'));bind('#profileDelete',async()=>{if(await confirmAction('Delete '+p.title+'?','Deletes only this saved profile. Instruments, PC banks and device data stay intact. You can Undo this change.'))await loadoutAction('delete',{id:p.id,confirmation:'Delete profile'});});
 bind('#profileFromBank',profileFromBank);
 bind('#profileExport',async()=>jsonDownload(p.title+'.fmer-loadout.json',await api('/api/loadouts',{action:'export',id:p.id})));
 bind('#profileImport',()=>chooseFile('.json',async file=>{const imported=JSON.parse(await file.text());await loadoutAction('import',{file:imported});loadoutId=loadouts.slots.at(-1).id;drawLoadouts();}));
 async function move(to){const next=structuredClone(p);next.slots.splice(to,0,next.slots.splice(loadoutSlot,1)[0]);loadoutSlot=to;await saveProfile(next);}
 bind('#profileUp',()=>move(loadoutSlot-1));bind('#profileDown',()=>move(loadoutSlot+1));bind('#profileMove',()=>move(Number($('#profileMoveTarget').value)));
 bind('#profileReplace',chooseProfileSound);bind('#profileAudition',()=>auditionProfileSound(chosen));
 bind('#profileForDefault',()=>{installProfile=p.id;drawLoadouts();});bind('#profileForUser',()=>{installUserProfile=p.id;drawLoadouts();});
 bind('#profileUseInstall',()=>{installProfile=p.id;changeView('firmware');});
 const assignments=document.createElement('section');assignments.className='panel';assignments.id='bankAssignments';$('#content').append(assignments);renderBankChoices(assignments).then(()=>{assignments.insertAdjacentHTML('beforeend','<button id="sendBankChoices" class="primary">Review &amp; apply bank choices?</button>');bind('#sendBankChoices',sendBankChoices);}).catch(fail);
}
async function auditionProfileSound(s){
 const audio=$('#profileAudio');audio.pause();notify('Rendering '+s.title+'…');
 const {state}=await api('/api/work',{action:'decode',entry:s.entry});
 const result=await api('/api/work',{action:'audition',entry:s.entry,state,scenario:'note',velocity:100});
 if(audio.isConnected){audio.src=result.audio_url;audio.volume=.35;await audio.play();notify('Preview uses the PC renderer; your instrument is unchanged.');}
}
async function chooseProfileSound(){
 await refresh();const sources=[...loadouts.sounds,...catalog.slots.filter(s=>s.kind==='instrument'&&!s.trashed).map(s=>slotSound(s.entry,s.title,s.notes)),...banks.slots.filter(Boolean).map(e=>slotSound(e,e.name,'PC sound bank snapshot'))];
 const dialog=document.createElement('dialog');dialog.className='loadout-picker';dialog.innerHTML=`<h2>Choose an instrument</h2><label>Search <input id="pickSearch" placeholder="Name or category"></label><select id="pickSound" size="12" aria-label="Replacement instrument"></select><div class="bar"><button id="pickListen">Listen</button><button id="pickApply" class="primary">Replace selected slot</button><button id="pickCancel">Cancel</button></div>`;document.body.append(dialog);
 const list=dialog.querySelector('#pickSound'),search=dialog.querySelector('#pickSearch');function filter(){list.innerHTML=sources.map((s,i)=>({s,i})).filter(({s})=>(s.title+' '+s.entry.name+' '+s.entry.category).toLowerCase().includes(search.value.toLowerCase())).map(({s,i})=>option(i,s.title+' · '+s.entry.category,-1)).join('');if(list.options.length)list.selectedIndex=0;dialog.querySelector('#pickApply').disabled=dialog.querySelector('#pickListen').disabled=!list.options.length;}
 search.oninput=filter;filter();dialog.showModal();search.focus();
 dialog.querySelector('#pickCancel').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();
 dialog.querySelector('#pickListen').onclick=run(async()=>auditionProfileSound(sources[Number(list.value)]));
 dialog.querySelector('#pickApply').onclick=run(async()=>{const p=structuredClone(currentProfile());p.slots[loadoutSlot]=structuredClone(sources[Number(list.value)]);await saveProfile(p);dialog.close();});
}
async function renderBankChoices(root,supported=true){
 const options=selected=>option('','Keep bank unchanged / compiled defaults on first install',selected)+profileList().map(p=>option(p.id,p.title,selected)).join('');
 root.innerHTML=`<h3>Choose each 64-instrument bank</h3><div class="bar"><label class="grow">Bank A <select id="installProfile" ${supported?'':'disabled'}>${options(installProfile)}</select></label><label class="grow">Bank B <select id="installUserProfile" ${supported?'':'disabled'}>${options(installUserProfile)}</select></label><button id="copyDefaultUser" ${supported?'':'disabled'}>Copy Bank A choice to Bank B</button></div><p class="muted">Each bank accepts FM or VA instruments. Choose different profiles, the same profile twice, or preserve either bank. Existing projects retain their slot references.</p>`;
 $('#installProfile').onchange=()=>installProfile=$('#installProfile').value;$('#installUserProfile').onchange=()=>installUserProfile=$('#installUserProfile').value;
 bind('#copyDefaultUser',()=>{installUserProfile=installProfile;$('#installUserProfile').value=installUserProfile;});
}
async function chosenBankPlan(){
 const request={default:installProfile?await api('/api/loadouts',{action:'export',id:installProfile}):null,user:installUserProfile?await api('/api/loadouts',{action:'export',id:installUserProfile}):null};
 if(!request.default&&!request.user)return null;
 const plan=await api('/api/loadout-banks-plan',request);return {request:{...request,confirmation:plan.confirmation},plan};
}
function bankChoiceSummary(request){return ['default','user'].map(k=>request[k]?(k==='default'?'Bank A':'Bank B')+': '+request[k].payload.title+' (64 replacements)':(k==='default'?'Bank A':'Bank B')+': keep unchanged').join('; ');}
async function sendBankChoices(){
 const chosen=await chosenBankPlan();if(!chosen)throw Error('Choose a profile for at least one bank.');
 if(await confirmAction('Apply both bank choices?',bankChoiceSummary(chosen.request)+'. Back up the complete unit, replace and verify the selected slots, then restore the working state. Projects keep slot references and may sound different. Keep USB connected; this can take several minutes.')){
  const rows=['default','user'].flatMap(k=>chosen.request[k]?chosen.request[k].payload.slots.map((s,i)=>({kind:'instrument',slot:(k==='default'?64:0)+i,entry:s.entry})):[]);
  await deviceJob({action:'deploy_library',rows,confirmation:chosen.plan.confirmation});
 }
}
async function drawInstallLoadouts(){
 await fetchLoadouts();const root=$('#installLoadouts');if(!root)return;
 const supported=inspection?.release_profile&&['fm1-compatible-to-734-r1','fm1-compatible-to-734-r3','fm1-compatible-to-735-r1','fm1-compatible-to-735-r2','fm1-compatible-to-735-r3','fm1-compatible-to-735-r4','fm1-compatible-to-735-r5','fm1-compatible-to-735-r6','fm1-compatible-to-735-r7','fm1-compatible-to-735-r8','fm1-compatible-to-735-r9'].includes(inspection.release_profile);
 await renderBankChoices(root,supported);
 root.insertAdjacentHTML('beforeend',`<button id="installReviewProfile">Review or customize profiles</button><p class="muted">${supported?'Optional: after installation, back up the initialized banks and apply your choices. Reflashing also backs up existing FMER saves before firmware installation. Bank transfer can take several minutes.':'Inspect the included FMER package to choose loadouts. Stock and custom firmware do not receive automatic profile writes.'}</p>`);
 bind('#installReviewProfile',()=>{if(installProfile)loadoutId=installProfile;changeView('loadouts');});
}
async function installWithLoadout(){
 const supported=['fm1-compatible-to-734-r1','fm1-compatible-to-734-r3','fm1-compatible-to-735-r1','fm1-compatible-to-735-r2','fm1-compatible-to-735-r3','fm1-compatible-to-735-r4','fm1-compatible-to-735-r5','fm1-compatible-to-735-r6','fm1-compatible-to-735-r7','fm1-compatible-to-735-r8','fm1-compatible-to-735-r9'].includes(inspection.release_profile);
 const chosen=supported?await chosenBankPlan():null;
 const detail=chosen?bankChoiceSummary(chosen.request)+'. Existing FMER saves are backed up first. Projects keep their slot references, so their sounds may change. These profiles are frozen snapshots for this operation.':'Existing instrument slots are kept; a first installation initializes the compiled defaults. Back up FMER saves first.';
 if(await confirmAction('Install '+inspection.product+'?',`${detail} Connect only the intended unit and leave power and USB connected. Stock firmware does not expose native backups. ${inspection.compatible_profile?'Custom application: saved-data and library compatibility are unqualified.':''}`)){
  const request={action:'install',inspection:inspection.inspection,confirmation:'Install '+inspection.product};if(chosen)request.loadout=chosen.request;
  const job=await api('/api/jobs',unitRequest(request));await waitJob(job.id);
 }
}
