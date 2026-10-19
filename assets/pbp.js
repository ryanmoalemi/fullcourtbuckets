(()=>{const D=window.PBP,f=document.getElementById('flt'),tb=document.querySelector('#pl tbody'),cnt=document.getElementById('count');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const KEYS=['q','player','team','type','period','run','scoring','swing','clutch','oldest'];
function read(){const p=new URLSearchParams(location.search);KEYS.forEach(k=>{const el=f.elements[k];if(!el)return;if(el.type==='checkbox')el.checked=p.get(k)==='1';else el.value=p.get(k)||''});}
function state(){const s={};KEYS.forEach(k=>{const el=f.elements[k];s[k]=el.type==='checkbox'?(el.checked?'1':''):el.value.trim()});return s}
function match(r,s){if(s.q){const w=s.q.toLowerCase().split(/\s+/);const t=(r.x+' '+r.k+' '+r.t).toLowerCase();if(!w.every(x=>t.includes(x)))return false}
if(s.player&&!r.ps.includes(s.player))return false;if(s.team&&r.t!==s.team)return false;
if(s.type){if(s.type==='shots'){if(!/PT|FT/.test(r.k))return false}else if(s.type==='made'||s.type==='missed'){if(!r.k.startsWith(s.type))return false}else if(r.k!==s.type)return false}
if(s.period&&String(r.q)!==s.period)return false;if(s.run){const[a,b]=s.run.split('-').map(Number);if(r.o<a||r.o>b)return false}
if(s.scoring==='1'&&!r.s)return false;if(s.swing==='1'&&!r.f)return false;if(s.clutch==='1'&&!r.cl)return false;return true}
let cur=[];
function render(push){const s=state();cur=D.rows.filter(r=>match(r,s));if(s.oldest!=='1')cur=cur.slice().reverse();
let h='',lq=null;for(const r of cur){if(r.q!==lq){h+=`<tr class="qh"><td colspan="5">${D.q[r.q]}</td></tr>`;lq=r.q}
h+=`<tr id="play-${r.o}" class="${r.s?'sc '+r.t:''}"><td class="c">${D.q[r.q]} ${esc(r.c)}</td><td class="t">${esc(r.t)}</td><td class="x">${esc(r.x)}${r.f?`<span class="tag">${r.f}</span>`:''}${r.cl&&s.clutch==='1'?'<span class="tag cl">clutch</span>':''}</td><td class="s">${r.a}-${r.h}</td><td class="l"><a href="#play-${r.o}" title="Permalink">#</a> <button class="cp" data-o="${r.o}" title="Copy citation">Cite</button></td></tr>`}
tb.innerHTML=h||'<tr><td colspan="5">No plays match these filters.</td></tr>';cnt.textContent=cur.length+' of '+D.rows.length+' plays';
if(push){const p=new URLSearchParams();KEYS.forEach(k=>s[k]&&p.set(k,s[k]));history.replaceState(null,'',(p.toString()?'?'+p:location.pathname)+location.hash)}}
function toast(t){const e=document.getElementById('toast');e.textContent=t;e.hidden=false;clearTimeout(toast.t);toast.t=setTimeout(()=>e.hidden=true,1800)}
function dl(name,type,text){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click()}
const COLS=['order','period','clock','team','play','away_score','home_score','type','scoring','flag','clutch'];
const row=r=>[r.o,r.q,r.c,r.t,r.x,r.a,r.h,r.k,r.s,r.f,r.cl];
f.addEventListener('input',()=>render(true));f.addEventListener('change',()=>render(true));
document.getElementById('reset').onclick=()=>{f.reset();render(true)};
document.getElementById('csv').onclick=()=>{const q=v=>{v=String(v??'');return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v};
dl(''+D.file+'.csv','text/csv','# '+D.title+'. Full Court Buckets, CC BY 4.0. '+location.href+'\n'+COLS.join(',')+'\n'+cur.map(r=>row(r).map(q).join(',')).join('\n')+'\n')};
document.getElementById('json').onclick=()=>dl(''+D.file+'.json','application/json',JSON.stringify({title:D.title,source:'Full Court Buckets',license:'CC BY 4.0',url:location.href,plays:cur.map(r=>Object.fromEntries(COLS.map((c,i)=>[c,row(r)[i]])))},null,1));
tb.addEventListener('click',e=>{const b=e.target.closest('.cp');if(!b)return;const r=D.rows.find(x=>x.o==b.dataset.o);
const t=`"${r.x}" (${D.q[r.q]}, ${r.c}; ${D.an} ${r.a}, ${D.hn} ${r.h}). ${D.title}, Full Court Buckets, ${D.date}. ${D.url}#play-${r.o}`;
(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>toast('Citation copied'),()=>prompt('Copy citation',t))});
document.querySelectorAll('[data-player]').forEach(b=>b.onclick=()=>{f.elements.player.value=b.dataset.player;render(true);f.scrollIntoView({behavior:'smooth'})});
const fb=document.getElementById('fbtn');const nOn=()=>KEYS.filter(k=>k!=='oldest'&&state()[k]).length;
const lab=()=>{const n=nOn();fb.textContent=n?`Filter (${n})`:'Filter'};fb.onclick=()=>{const o=f.classList.toggle('open');fb.setAttribute('aria-expanded',o)};
f.addEventListener('change',lab);f.addEventListener('input',lab);
read();render(false);lab();if(location.hash){const el=document.querySelector(location.hash);el&&el.scrollIntoView()}})();
