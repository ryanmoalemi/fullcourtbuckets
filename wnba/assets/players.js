/* Progressive enhancement only. All player statistics and links are in static HTML. */
'use strict';
document.documentElement.classList.add('js');
const season=document.getElementById('season-filter');
let competition='all';
function filterStats(){
  let total=0;
  document.querySelectorAll('[data-competition]').forEach(panel=>{
    let found=0;
    panel.querySelectorAll('[data-season]').forEach(row=>{
      const match=!season||season.value==='all'||season.value===row.dataset.season;
      row.hidden=!match;if(match)found++;
    });
    panel.hidden=(competition!=='all'&&panel.dataset.competition!==competition)||found===0;
    if(!panel.hidden)total+=found;
  });
  const empty=document.getElementById('stats-empty');
  if(empty)empty.hidden=total>0;
}
document.querySelectorAll('[data-kind]').forEach(button=>button.addEventListener('click',()=>{
  competition=button.dataset.kind;
  document.querySelectorAll('[data-kind]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));
  filterStats();
}));
if(season)season.addEventListener('change',filterStats);
const search=document.getElementById('player-search');
const active=document.getElementById('active-filter');
const normalize=value=>value.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9 ]/g,'');
function visibleRows(root){
  return [...root.querySelectorAll('.player-row')].some(row=>!row.hidden);
}
function filterPlayers(){
  const term=normalize(search?.value||'');
  const mode=active?active.value:'all';
  let count=0;
  document.querySelectorAll('.player-row[data-search]').forEach(row=>{
    const match=normalize(row.dataset.search).includes(term)&&(mode==='all'||row.dataset.active===mode);
    row.hidden=!match;
    if(match)count++;
  });
  document.querySelectorAll('.az-group').forEach(group=>{group.hidden=!visibleRows(group);});
  const featured=document.getElementById('featured-players');
  if(featured)featured.hidden=!visibleRows(featured);
  const inactive=document.getElementById('inactive-players');
  if(inactive){
    const any=visibleRows(inactive);
    inactive.hidden=mode==='true'?!any&&!!term:!any;
    if(mode==='false'||(term&&any))inactive.open=true;
    if(mode==='true'&&!term)inactive.open=false;
  }
  const result=document.getElementById('result-count');
  if(result)result.textContent=`${count} ${count===1?'profile':'profiles'}`;
  const empty=document.getElementById('no-players');
  if(empty)empty.hidden=count>0;
}
if(search)search.addEventListener('input',filterPlayers);
if(active)active.addEventListener('change',filterPlayers);
const share=document.getElementById('share');
if(share)share.addEventListener('click',async()=>{
  const canonical=document.querySelector('link[rel=canonical]')?.href||location.href;
  const status=document.getElementById('share-status');
  try{
    if(navigator.share){await navigator.share({title:document.title,url:canonical});status.textContent='';}
    else if(navigator.clipboard){await navigator.clipboard.writeText(canonical);status.textContent='Link copied.';}
    else status.textContent='Copy the page address from your browser.';
  }catch(error){if(error.name!=='AbortError')status.textContent='Copy the page address from your browser.';}
});
