"""Generate an offline audition desk for original FMER sound collections.

The page has no hardware, network or Companion-library side effects. Review
exports are declarative input to the collection builder, not device writes.
SPDX-License-Identifier: GPL-3.0-only
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


def _relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or any(c in value for c in "\\:#?%\x00") or any(ord(c) < 32 for c in value):
        raise ValueError("Review media and download paths must be local relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in (".", "..") for part in path.parts):
        raise ValueError("Review paths must remain inside the review folder")
    return value


def validate_manifest(manifest: dict) -> None:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), str):
        raise ValueError("Review manifest needs a string version")
    patches = manifest.get("patches")
    collections = manifest.get("collections")
    if not isinstance(patches, list) or not patches or not isinstance(collections, list):
        raise ValueError("Review manifest needs patches and collections")
    identifiers: set[str] = set()
    for patch in patches:
        if not isinstance(patch, dict) or not isinstance(patch.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", patch["id"]) or patch["id"] in ("constructor", "prototype"):
            raise ValueError("Every review patch needs a nonempty string ID")
        if patch["id"] in identifiers:
            raise ValueError("Review patch IDs must be unique")
        identifiers.add(patch["id"])
        if patch.get("engine") not in ("FM", "VA"):
            raise ValueError("Review engine must be FM or VA")
        if not isinstance(patch.get("name"), str) or not patch["name"]:
            raise ValueError("Every review patch needs a name")
        for clip in patch.get("clips", []):
            _relative_path(clip.get("path"))
    collection_ids: set[str] = set()
    for collection in collections:
        if not isinstance(collection, dict) or not isinstance(collection.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", collection["id"]) or collection["id"] in ("constructor", "prototype"):
            raise ValueError("Every collection needs an ID")
        if collection["id"] in collection_ids:
            raise ValueError("Collection IDs must be unique")
        collection_ids.add(collection["id"])
        if not isinstance(collection.get("patch_ids"), list) or not collection["patch_ids"]:
            raise ValueError("Every collection needs an ordered patch list")
        if any(identifier not in identifiers for identifier in collection["patch_ids"]):
            raise ValueError("Collection references an unknown patch")
    for download in manifest.get("downloads", []):
        _relative_path(download.get("path"))


def write_review(output_dir: Path, manifest: dict) -> Path:
    """Write one self-contained HTML page; audio/catalog files stay adjacent.

    The manifest contract is intentionally independent of recipe generation.
    JSON is escaped for a script element; user strings enter the DOM through
    textContent. Imported curation is bounded and validated before replacement.
    """
    validate_manifest(manifest)
    encoded = json.dumps(manifest, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    title = html.escape(str(manifest.get("title", "FMER sound collections")))
    result = _PAGE.replace("__PAGE_TITLE__", title).replace("__MANIFEST_JSON__", encoded)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "index.html"
    destination.write_text(result, encoding="utf-8")
    return destination


_PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><title>__PAGE_TITLE__</title>
<style>
:root{--bg:#070709;--panel:#101014;--alt:#1b1b23;--field:#09090d;--hover:#30313a;--border:#727684;--text:#f5f7fa;--muted:#b6bbc6;--green:#76ff53;--pink:#ff78d4;--purple:#c9a0ff;--grid:#202127;--axis:#4b4e5a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,Segoe UI,sans-serif}button,input,select,textarea{font:inherit}button,a,input,select,textarea{touch-action:manipulation}button,select,input[type=search],textarea{background:var(--field);border:1px solid var(--border);border-radius:3px;color:var(--text)}button{cursor:pointer;padding:8px 12px;min-height:40px}button:hover{background:var(--hover)}button:disabled{opacity:.5;cursor:default}a{color:var(--green)}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid var(--pink);outline-offset:3px}button[aria-pressed=true]{border-color:var(--pink);background:#382233;box-shadow:inset 0 0 0 1px var(--pink)}button.primary{color:var(--bg);background:var(--green);border-color:var(--green);font-weight:700}button.primary:hover{background:#adff98}h1,h2,h3,p{margin:0}h1{font-size:24px;line-height:1.2}h2{font-size:20px}h3{font-size:16px}header{border-bottom:1px solid var(--axis);padding:18px 24px;display:flex;gap:20px;align-items:center;justify-content:space-between}.brand{display:flex;align-items:center;gap:20px}.wordmark{font-size:32px;font-weight:900;letter-spacing:3px;color:var(--green)}.muted{color:var(--muted)}.small{font-size:12px}.badge{border:1px solid var(--axis);border-radius:3px;padding:2px 7px;font-size:12px;white-space:nowrap}.badge.fm{color:var(--green)}.badge.va{color:var(--purple)}.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:700}.toolbar,.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.toolbar{padding:14px 24px;border-bottom:1px solid var(--grid);justify-content:space-between}.tabs{display:flex;gap:6px;flex-wrap:wrap}.tabs button{min-width:48px}.page{padding:18px 24px 36px;max-width:1800px;margin:auto}.intro{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:16px}.intro p{max-width:780px;color:var(--muted);margin-top:4px}.workspace{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:18px;align-items:start}.catalog{min-width:0}.filters{display:grid;grid-template-columns:minmax(150px,1fr) 90px 150px 130px;gap:8px;background:var(--panel);border:1px solid var(--grid);padding:12px;border-radius:3px}.field label{display:block;font-size:12px;color:var(--muted);margin-bottom:4px}.field input,.field select{width:100%;height:40px;padding:7px}.countline{display:flex;justify-content:space-between;gap:10px;margin:10px 2px;color:var(--muted);font-size:12px}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(205px,1fr));gap:9px}.card{min-width:0;background:var(--panel);border:1px solid var(--grid);border-radius:3px;overflow:hidden}.card.selected{border:2px solid var(--pink)}.card button{border:0;border-radius:0;width:100%;text-align:left;padding:12px;background:transparent;min-height:122px}.card button:hover{background:var(--alt)}.card-title{overflow-wrap:anywhere;font-size:16px;font-weight:700;display:block;margin:7px 0 4px;line-height:1.25}.card-top{display:flex;justify-content:space-between;gap:8px;align-items:center}.card-meta{font-size:12px;color:var(--muted);display:block}.card-state{font-size:12px;color:var(--pink);margin-top:6px;display:block}.inspector{position:sticky;top:12px;background:var(--panel);border:1px solid var(--axis);border-radius:3px;padding:17px}.inspector .description{color:var(--muted);margin-top:12px}.inspector h2{margin-top:9px;font-size:25px;line-height:1.15;overflow-wrap:anywhere}.inspector .subtitle{margin-top:5px;font-size:12px;color:var(--muted)}.section{padding-top:14px;margin-top:14px;border-top:1px solid var(--grid)}.audio-clips{display:flex;gap:6px;flex-wrap:wrap;margin:9px 0}.audio-clips button{font-size:13px;padding:7px 9px}audio{width:100%;height:40px}.volume{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center;margin-top:8px}.volume input{width:100%;accent-color:var(--green)}.volume label{grid-column:1/-1;font-size:12px;color:var(--muted)}.rating-buttons{display:flex;gap:7px;margin:9px 0}.rating-buttons button{flex:1}.notes{width:100%;resize:vertical;min-height:88px;padding:9px;margin-top:5px}.note-label{font-size:12px;color:var(--muted)}.status{font-size:12px;color:var(--muted);min-height:18px;margin-top:7px}.status.error{color:var(--pink)}.metrics{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:9px}.metric{background:var(--field);padding:7px;border:1px solid var(--grid);border-radius:3px}.metric span{display:block}.metric strong{font-variant-numeric:tabular-nums;font-size:13px}details{margin-top:10px}summary{cursor:pointer;color:var(--muted);font-size:13px}details p{font-size:13px;margin-top:6px;color:var(--muted)}.pagination{display:flex;justify-content:space-between;margin-top:10px}.no-results{padding:30px;text-align:center;color:var(--muted);border:1px dashed var(--axis);grid-column:1/-1}.downloads{display:flex;gap:15px;flex-wrap:wrap;margin-top:8px;font-size:13px}.qualification{margin-top:22px;padding:14px;border:1px solid var(--grid);background:var(--panel);border-radius:3px;font-size:13px;color:var(--muted)}.qualification strong{color:var(--text)}.qualification ul{margin:7px 0 0;padding-left:20px}.sheet{width:min(1050px,95vw);max-height:88vh;background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:3px;padding:0}.sheet::backdrop{background:#000b}.sheet-head{padding:16px;display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid var(--axis);position:sticky;top:0;background:var(--panel);z-index:1}.sheet-body{padding:16px}.slot-table{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.slot-row{display:grid;grid-template-columns:32px minmax(0,1fr) 52px;gap:7px;align-items:center}.slot-row select{width:100%;padding:7px;min-height:40px;font-size:13px}.slot-number{color:var(--muted);font-variant-numeric:tabular-nums}.slot-row button{padding:6px}.warning{border-left:3px solid var(--pink);padding-left:10px;margin:0 0 14px;color:var(--muted);font-size:13px}.quiet{font-size:12px}#toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:var(--alt);border:1px solid var(--green);padding:10px 16px;border-radius:3px;z-index:10;max-width:90vw}#toast[hidden]{display:none}.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:1100px){.filters{grid-template-columns:1fr 85px}.workspace{grid-template-columns:minmax(0,1fr) 350px}.brand{gap:12px}header{align-items:flex-start}.cards{grid-template-columns:repeat(auto-fill,minmax(175px,1fr))}}
@media(max-width:760px){header,.toolbar{padding:12px}.brand{align-items:flex-start}.wordmark{font-size:24px}h1{font-size:19px}.page{padding:12px}.workspace{display:flex;flex-direction:column}.catalog{width:100%}.inspector{position:static;width:100%;order:-1}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.card button{min-height:132px;padding:10px}.intro{display:block}.intro>button{margin-top:10px}.slot-table{grid-template-columns:1fr}.toolbar{gap:12px}header>.badge{display:none}.qualification{margin-top:14px}}
</style></head><body>
<header><div class="brand"><span class="wordmark">FMER</span><div><h1>__PAGE_TITLE__</h1><p class="muted small" id="edition"></p></div></div><span class="badge">Offline audition desk</span></header>
<div class="toolbar"><nav class="tabs" id="collections" aria-label="Sound collection"></nav><div class="row"><a href="#downloads" class="quiet">Download sounds</a><button id="undo" disabled>Undo review edit</button><button id="export" class="primary">Export review</button><button id="import">Import review</button><input id="import-file" type="file" accept=".json,application/json" hidden></div></div>
<main class="page"><section class="intro"><div><h2 id="collection-title"></h2><p id="collection-description"></p></div><button id="slots" disabled>Review loadout slots</button></section>
<div class="workspace"><section class="catalog" aria-label="Sound catalog"><div class="filters">
<div class="field"><label for="search">Find a sound or texture</label><input id="search" type="search" placeholder="Bass, glass, evolving…" autocomplete="off"></div>
<div class="field"><label for="engine">Engine</label><select id="engine"><option value="">All</option><option>FM</option><option>VA</option></select></div>
<div class="field"><label for="family">Family</label><select id="family"><option value="">All families</option></select></div>
<div class="field"><label for="review-filter">Review</label><select id="review-filter"><option value="">Everything</option><option value="favorite">Favorites</option><option value="unreviewed">Unreviewed</option><option value="keep">Keep</option><option value="rework">Rework</option><option value="pass">Pass</option><option value="measured-flags">Measurement flags</option></select></div>
</div><div class="countline"><span id="result-count"></span><span id="review-count"></span></div><div class="cards" id="cards"></div></section>
<aside class="inspector" id="inspector" aria-label="Selected sound"><div class="row" style="justify-content:space-between"><span id="detail-engine" class="badge"></span><button id="favorite" aria-pressed="false" title="Mark this sound as a favorite">☆ Favorite</button></div>
<h2 id="detail-title"></h2><p class="subtitle" id="detail-subtitle"></p><p class="description" id="detail-description"></p><details><summary>Sound design</summary><p id="detail-technique"></p></details>
<div class="section"><div class="eyebrow">Audition</div><div class="audio-clips" id="clips"></div><audio id="player" controls preload="none" aria-label="Selected sound audio"></audio><p class="status" id="audio-status" role="status"></p><div class="volume"><label for="volume">Listening volume · source levels retained</label><input id="volume" type="range" min="0" max="100" value="65"><output id="volume-value" for="volume">65%</output></div><div id="metrics" class="metrics"></div><p class="small muted" id="audition-note" style="margin-top:8px"></p><div id="measurement-flags" class="warning" style="margin:10px 0 0" hidden></div><details id="measurement-details" hidden><summary>Measured checks</summary><p id="measurement-summary"></p></details></div>
<div class="section"><div class="eyebrow">Your review</div><div class="rating-buttons"><button data-rating="keep" aria-pressed="false">Keep</button><button data-rating="rework" aria-pressed="false">Rework</button><button data-rating="pass" aria-pressed="false">Pass</button></div><label for="notes" class="note-label">What works? What should change?</label><textarea id="notes" class="notes" maxlength="6000" placeholder="Tone, attack, expression, useful register…"></textarea><p class="status" id="save-status" role="status"></p><div class="pagination"><button id="previous" aria-label="Previous sound">← Previous</button><button id="next" aria-label="Next sound">Next →</button></div></div></aside></div>
<section class="qualification"><strong>What you are hearing</strong><p id="scope" style="margin-top:6px">These are rendered previews of the stored instruments. Listening volume is a monitor control; it does not change patch gain. Playback does not access or alter an FM-1.</p><ul id="qualification-list"></ul><p style="margin-top:10px">Review edits are kept in this browser when local storage is available. Export your review to keep a portable copy. Moving this folder or using another browser may create a separate review.</p><details><summary>Use these sounds in Companion</summary><p>Import the catalog download into Companion's Library, review the sounds, then use Sound banks to assemble or load the supplied bank file. Review the destination and back up the unit before deploying a bank. This audition page never writes to a device.</p><p>Loadout slot edits are saved in your review export. They do not modify the downloadable native bank files until those files are rebuilt from that export.</p></details><div class="downloads" id="downloads"></div></section>
</main><dialog class="sheet" id="slot-dialog"><div class="sheet-head"><div><h2 id="slot-title"></h2><p class="small muted">Display slots start at 1. The export preserves their exact order.</p></div><button id="close-slots">Close</button></div><div class="sheet-body"><p class="warning">These are your proposed loadout changes. Export the review to rebuild the bank; the existing download stays unchanged.</p><div class="slot-table" id="slot-table"></div></div></dialog><div id="toast" role="status" hidden></div>
<script id="manifest" type="application/json">__MANIFEST_JSON__</script><script>
'use strict';
(() => {
 const manifest=JSON.parse(document.getElementById('manifest').textContent), byId=new Map(manifest.patches.map(p=>[p.id,p]));
 const $=id=>document.getElementById(id), player=$('player'), key='fmer-sound-curation:v1:'+manifest.version;
 const ratingsAllowed=new Set(['','keep','rework','pass']), own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
 const defaultCollections=()=>Object.fromEntries(manifest.collections.map(c=>[c.id,c.patch_ids.slice()]));
 let review={ratings:{},collections:defaultCollections()}, undo=[], selected=manifest.patches[0].id, collection='', filtered=[], selectedClip=null, toastTimer;
 let storageOK=true, notesBefore='', notesOwner=selected;
 const text=(element,value)=>{element.textContent=value==null?'':String(value);};
 const node=(tag,cls,value)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(value!=null)text(e,value);return e;};
 const clone=o=>JSON.parse(JSON.stringify(o));
 const rating=id=>own(review.ratings,id)?review.ratings[id]:{rating:'',favorite:false,notes:''};
 const title=p=>p.title||p.name;
 function toast(message){text($('toast'),message);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
 function validateReview(data){
  if(!data||data.format!=='FMER-SOUND-CURATION'||data.schema!==1)throw Error('This is not an FMER sound review file.');
  if(data.library_version!==manifest.version)throw Error('This review belongs to a different library version. Use its matching audition folder.');
  if(!data.ratings||typeof data.ratings!=='object'||Array.isArray(data.ratings)||!data.collections||typeof data.collections!=='object'||Array.isArray(data.collections))throw Error('The review is missing its ratings or loadouts.');
  const valid={ratings:Object.create(null),collections:Object.create(null)};
  if(Object.keys(data.ratings).length>manifest.patches.length)throw Error('The review contains too many patch ratings.');
  for(const [id,value] of Object.entries(data.ratings)){
   if(!byId.has(id)||!value||typeof value!=='object'||!ratingsAllowed.has(value.rating)||typeof value.favorite!=='boolean'||typeof value.notes!=='string'||value.notes.length>6000)throw Error('The review contains an unknown patch or invalid rating.');
   valid.ratings[id]={rating:value.rating,favorite:value.favorite,notes:value.notes};
  }
  if(Object.keys(data.collections).length!==manifest.collections.length)throw Error('The review does not contain the expected loadouts.');
  for(const c of manifest.collections){
   const ids=own(data.collections,c.id)?data.collections[c.id]:null;
   if(!Array.isArray(ids)||ids.length!==c.patch_ids.length||ids.some(id=>typeof id!=='string'||!byId.has(id)))throw Error('Loadout '+c.id+' has an invalid slot count or unknown sound.');
   valid.collections[c.id]=ids.slice();
  }
  return valid;
 }
 function exportData(){return {format:'FMER-SOUND-CURATION',schema:1,library_version:manifest.version,exported_at:new Date().toISOString(),ratings:clone(review.ratings),collections:clone(review.collections)};}
 function persist(){
  try{localStorage.setItem(key,JSON.stringify(exportData()));storageOK=true;}catch(error){storageOK=false;}
  text($('save-status'),storageOK?'Saved in this browser. Export to keep a portable copy.':'Browser storage is unavailable. Export your review before closing.');
  $('save-status').classList.toggle('error',!storageOK);$('undo').disabled=!undo.length;
 }
 function mutate(change){undo.push(clone(review));if(undo.length>50)undo.shift();change();persist();renderCards();renderCounts();}
 function writeRating(id,changes){const value={...rating(id),...changes};if(value.rating||value.favorite||value.notes)review.ratings[id]=value;else delete review.ratings[id];}
 function commitNotes(){const value=$('notes').value;if(value!==notesBefore){const id=notesOwner;mutate(()=>writeRating(id,{notes:value}));notesBefore=value;}}
 function stopAudio(){document.querySelectorAll('[data-clip]').forEach(b=>b.setAttribute('aria-pressed','false'));player.pause();player.removeAttribute('src');player.load();selectedClip=null;text($('audio-status'),'Choose an audition to play.');}
 function renderCounts(){text($('result-count'),filtered.length+' sounds'+(collection?' in collection '+collection:''));const r=Object.values(review.ratings);text($('review-count'),r.filter(x=>x.rating).length+' / '+manifest.patches.length+' reviewed · '+r.filter(x=>x.favorite).length+' favorites');}
 function renderCards(){
  const search=$('search').value.trim().toLowerCase(),engine=$('engine').value,family=$('family').value,filter=$('review-filter').value;
  let ids=collection?Array.from(new Set(review.collections[collection])):manifest.patches.map(p=>p.id);
  filtered=ids.filter(id=>{const p=byId.get(id),r=rating(id),terms=[p.name,p.title,p.category,p.family,p.description,...(p.tags||[])].join(' ').toLowerCase();return (!search||terms.includes(search))&&(!engine||p.engine===engine)&&(!family||p.family===family)&&(!filter||(filter==='favorite'?r.favorite:filter==='unreviewed'?!r.rating:filter==='measured-flags'?Boolean(p.metrics?.failures?.length||p.metrics?.warnings?.length):r.rating===filter));});
  const cards=$('cards');cards.replaceChildren();
  for(const id of filtered){const p=byId.get(id),r=rating(id),article=node('article','card'+(id===selected?' selected':'')),button=node('button');button.type='button';button.dataset.patch=id;button.setAttribute('aria-pressed',String(id===selected));const top=node('span','card-top');top.append(node('span','badge '+p.engine.toLowerCase(),p.engine),node('span','small muted',r.favorite?'★ Favorite':p.category||p.family));button.append(top,node('span','card-title',title(p)),node('span','card-meta',p.family||p.category||''));if(p.metrics?.failures?.length||p.metrics?.warnings?.length)button.append(node('span','card-state',p.metrics?.failures?.length?'Audio check flagged':'Level review'));if(r.rating)button.append(node('span','card-state',r.rating==='keep'?'Keep':r.rating==='rework'?'Rework':'Pass'));article.append(button);cards.append(article);}
  if(!filtered.length)cards.append(node('p','no-results','No sounds match these filters. Try another family or clear the search.'));
  renderCounts();$('previous').disabled=!filtered.length;$('next').disabled=!filtered.length;
 }
 function number(value){return Number.isFinite(Number(value))?Number(value).toFixed(4):'—';}
 function renderMetrics(clip){const box=$('metrics');box.replaceChildren();if(!clip)return;for(const [label,value] of [['Peak',clip.peak],['RMS',clip.rms]]){if(value==null)continue;const m=node('div','metric');m.append(node('span','eyebrow',label),node('strong','',number(value)+' FS'));box.append(m);}}
 function renderMeasurementFlags(p){const m=p.metrics||{},flags=[...(m.failures||[]),...(m.warnings||[])];text($('measurement-flags'),flags.join(' ? '));$('measurement-flags').hidden=!flags.length;$('measurement-details').hidden=!Object.keys(m).length;const pieces=[];if(m.render_count!=null)pieces.push(m.render_count+' measured renders');if(m.peak!=null)pieces.push('Highest measured peak '+number(m.peak)+' FS (all test cases)');if(m.dry_centroid_hz!=null)pieces.push('Dry spectral centroid '+m.dry_centroid_hz+' Hz');if(m.release_end_rms!=null)pieces.push('End-of-release RMS '+number(m.release_end_rms)+' FS');text($('measurement-summary'),pieces.join(' ? '));}
 function renderRating(){const r=rating(selected);$('favorite').setAttribute('aria-pressed',String(r.favorite));text($('favorite'),r.favorite?'★ Favorite':'☆ Favorite');document.querySelectorAll('[data-rating]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.rating===r.rating)));$('notes').value=r.notes;notesBefore=r.notes;notesOwner=selected;}
 function showPatch(id){if(!byId.has(id))return;commitNotes();stopAudio();selected=id;const p=byId.get(id);text($('detail-engine'),p.engine);$('detail-engine').className='badge '+p.engine.toLowerCase();text($('detail-title'),title(p));text($('detail-subtitle'),p.name+' · '+(p.family||p.category||'')+' · '+p.id);text($('detail-description'),p.description||'');text($('detail-technique'),p.technique||'No additional technique notes.');text($('audition-note'),Number.isFinite(p.audition_note)?'Reference MIDI note '+p.audition_note+(p.audition_note_label?' ('+p.audition_note_label+')':''):(p.audition_note||''));const clips=$('clips');clips.replaceChildren();(p.clips||[]).forEach((clip,index)=>{const b=node('button','',clip.label||clip.kind||('Audition '+(index+1)));b.type='button';b.dataset.clip=index;clips.append(b);});if(!p.clips?.length)text($('audio-status'),'Audio has not been rendered for this sound.');renderMetrics(p.clips?.[0]);renderMeasurementFlags(p);renderRating();renderCards();}
 function playClip(index){const p=byId.get(selected),clip=p.clips?.[index];if(!clip)return;player.pause();document.querySelectorAll('[data-clip]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.clip)===index)));selectedClip=clip;player.src=clip.path;player.volume=Number($('volume').value)/100;renderMetrics(clip);text($('audio-status'),'Loading '+(clip.label||'audition')+'…');player.play().catch(()=>text($('audio-status'),'Playback could not start. Keep the audio folder beside this page and use the player controls.'));}
 function chooseCollection(id){commitNotes();collection=id;document.querySelectorAll('[data-collection]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.collection===id)));const c=manifest.collections.find(c=>c.id===id);text($('collection-title'),c?c.title:'All original sounds');text($('collection-description'),c?c.description:'Explore the full library, compare expression and choose the sounds for your four loadouts.');$('slots').disabled=!c;renderCards();}
 function renderSlots(){const c=manifest.collections.find(c=>c.id===collection);if(!c)return;text($('slot-title'),c.title+' · '+review.collections[c.id].length+' slots');const box=$('slot-table');box.replaceChildren();const options=manifest.patches.slice().sort((a,b)=>(a.engine+' '+title(a)).localeCompare(b.engine+' '+title(b)));review.collections[c.id].forEach((id,index)=>{const row=node('div','slot-row'),sel=node('select');sel.dataset.slot=index;sel.setAttribute('aria-label','Slot '+(index+1)+' instrument');options.forEach(p=>{const o=node('option','',p.engine+' · '+title(p));o.value=p.id;sel.append(o);});sel.value=id;const audition=node('button','','View');audition.dataset.viewSlot=index;audition.setAttribute('aria-label','View slot '+(index+1));row.append(node('span','slot-number',String(index+1).padStart(2,'0')),sel,audition);box.append(row);});}
 function downloadReview(){commitNotes();const blob=new Blob([JSON.stringify(exportData(),null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=node('a');a.href=url;a.download='FMER-sound-review-'+manifest.version.replace(/[^a-zA-Z0-9._-]/g,'-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast('Review exported with your ratings, notes and loadout slots.');}
 try{const stored=localStorage.getItem(key);if(stored)review=validateReview(JSON.parse(stored));}catch(error){storageOK=false;toast('Saved review could not be read. Your exported review can be imported.');}
 text($('edition'),manifest.patches.length+' original sounds · '+manifest.collections.length+' loadouts · '+manifest.version);
 for(const c of [{id:'',title:'All sounds'},...manifest.collections]){const b=node('button','',c.id?c.id+' · '+c.title.replace(/^(?:Collection\s+)?[A-D]\s*[—:–\/-]\s*/i,''):c.title);b.dataset.collection=c.id;b.type='button';b.setAttribute('aria-pressed',String(!c.id));$('collections').append(b);}
 Array.from(new Set(manifest.patches.map(p=>p.family).filter(Boolean))).sort().forEach(f=>{const o=node('option','',f);o.value=f;$('family').append(o);});
 for(const d of manifest.downloads||[]){const a=node('a','',d.label);a.href=d.path;a.setAttribute('download','');$('downloads').append(a);}
 const qualification=manifest.qualification||{};for(const [label,value]of Object.entries(qualification)){if(value==null||typeof value==='object')continue;const li=node('li');li.append(node('strong','',label.replaceAll('_',' ')+': '),document.createTextNode(String(value)));$('qualification-list').append(li);}
 $('collections').addEventListener('click',e=>{const b=e.target.closest('[data-collection]');if(b)chooseCollection(b.dataset.collection);});
 ['search','engine','family','review-filter'].forEach(id=>$(id).addEventListener('input',renderCards));
 $('cards').addEventListener('click',e=>{const b=e.target.closest('[data-patch]');if(b){showPatch(b.dataset.patch);if(innerWidth<761)$('inspector').scrollIntoView({behavior:'smooth',block:'start'});}});
 $('clips').addEventListener('click',e=>{const b=e.target.closest('[data-clip]');if(b)playClip(Number(b.dataset.clip));});
 player.addEventListener('playing',()=>text($('audio-status'),'Playing '+(selectedClip?.label||'audition')+' · '+title(byId.get(selected))));
 player.addEventListener('ended',()=>text($('audio-status'),'Audition finished.'));
 player.addEventListener('error',()=>{if(player.hasAttribute('src'))text($('audio-status'),'Audio file unavailable. Extract the complete folder, including audio, then reopen index.html.');});
 $('volume').addEventListener('input',()=>{player.volume=Number($('volume').value)/100;text($('volume-value'),$('volume').value+'%');});
 $('favorite').addEventListener('click',()=>{commitNotes();mutate(()=>writeRating(selected,{favorite:!rating(selected).favorite}));renderRating();});
 document.querySelectorAll('[data-rating]').forEach(b=>b.addEventListener('click',()=>{commitNotes();mutate(()=>writeRating(selected,{rating:rating(selected).rating===b.dataset.rating?'':b.dataset.rating}));renderRating();}));
 $('notes').addEventListener('change',commitNotes);
 $('previous').addEventListener('click',()=>{if(filtered.length)showPatch(filtered[(Math.max(0,filtered.indexOf(selected))-1+filtered.length)%filtered.length]);});
 $('next').addEventListener('click',()=>{if(filtered.length)showPatch(filtered[(filtered.indexOf(selected)+1)%filtered.length]);});
 $('undo').addEventListener('click',()=>{commitNotes();if(undo.length){review=undo.pop();persist();renderRating();renderCards();if($('slot-dialog').open)renderSlots();toast('Last review edit undone.');}});
 $('export').addEventListener('click',downloadReview);
 $('import').addEventListener('click',()=>$('import-file').click());
 $('import-file').addEventListener('change',async()=>{const file=$('import-file').files[0];if(!file)return;try{if(file.size>4*1024*1024)throw Error('This file is too large to be a sound review.');const incoming=validateReview(JSON.parse(await file.text()));commitNotes();if(Object.keys(review.ratings).length&&!confirm('Replace the current review with this file? Undo remains available.'))return;mutate(()=>{review=incoming;});renderRating();toast('Review imported. Ratings, notes and loadout slots restored.');}catch(error){toast('Import not applied: '+error.message);}finally{$('import-file').value='';}});
 $('slots').addEventListener('click',()=>{commitNotes();renderSlots();$('slot-dialog').showModal();});$('close-slots').addEventListener('click',()=>$('slot-dialog').close());
 $('slot-table').addEventListener('change',e=>{const sel=e.target.closest('[data-slot]');if(!sel)return;const index=Number(sel.dataset.slot),id=sel.value;if(!byId.has(id))return;mutate(()=>{review.collections[collection][index]=id;});toast('Proposed slot updated. Export the review to rebuild this loadout.');});
 $('slot-table').addEventListener('click',e=>{const b=e.target.closest('[data-view-slot]');if(b){const id=review.collections[collection][Number(b.dataset.viewSlot)];$('slot-dialog').close();showPatch(id);}});
 addEventListener('beforeunload',()=>{commitNotes();});
 chooseCollection('');showPatch(selected);persist();
})();
</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(write_review(args.output, json.loads(args.manifest.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    main()
