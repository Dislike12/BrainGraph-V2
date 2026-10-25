const $ = (selector) => document.querySelector(selector);
const svgNS = 'http://www.w3.org/2000/svg';
const palette = {file:'#56e0b2',function:'#61cfe7',class:'#ffbd69',component:'#b99cff',api:'#ff7c94',route:'#ff9d69',module:'#71849a',asset:'#78a7d1',default:'#8a99a7'};
const state = { graph:null, stats:null, aiConfigured:false, scale:1, tx:0, ty:0, dragging:null, pan:null, toastTimer:null };

async function api(url, options={}) {
  const response = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}
function showToast(message) {
  const toast = $('#toast'); toast.textContent = message; toast.classList.add('visible');
  clearTimeout(state.toastTimer); state.toastTimer = setTimeout(() => toast.classList.remove('visible'), 3600);
}
function compactNumber(number) { return Number(number || 0).toLocaleString(); }
function languageColor(index) { return ['#56e0b2','#61cfe7','#b99cff','#ffbd69','#ff7c94','#78a7d1'][index % 6]; }

async function loadStatus() {
  const result = await api('/api/status');
  state.aiConfigured = result.ai_configured;
  $('#repoName').textContent = result.project_name || 'Waiting for terminal scan';
  $('#repoPath').textContent = result.project_path || 'Run braingraph scan .';
  $('#footerRepo').textContent = result.project_path || 'No repository selected';
  $('#repoState').textContent = result.indexed ? 'INDEXED / READY' : 'TERMINAL SCAN READY';
  $('#aiStatus').classList.toggle('configured', result.ai_configured);
  $('#aiStatus').innerHTML = `<i></i><span>${result.ai_configured ? `AI / ${escapeHtml(result.model)}` : 'Local mode'}</span>`;
  $('#providerLabel').textContent = result.ai_configured ? `AI / ${result.model}` : 'LOCAL RETRIEVAL';
  if (result.indexed) await refreshDashboard();
  else $('#repoHint').textContent = 'Use braingraph scan . in your project terminal.';
}
async function refreshDashboard() {
  const stats = await api('/api/stats');
  state.stats = stats;
  $('#fileCount').textContent = compactNumber(stats.files);
  $('#nodeCount').textContent = compactNumber(stats.nodes);
  $('#edgeCount').textContent = compactNumber(stats.edges);
  $('#railEdges').textContent = compactNumber(stats.edges);
  $('#fileHealth').textContent = `${stats.languages.length} LANGUAGES`;
  $('#scanTime').textContent = stats.scan_seconds == null ? 'TIMING N/A' : `${Number(stats.scan_seconds).toFixed(2)} SEC`;
  $('#diagnosticBadge').textContent = `${stats.diagnostics} FLAGS`;
  const usage = stats.usage || {requests:0,raw_tokens:0,context_tokens:0,saved_tokens:0};
  const savedPercent = usage.raw_tokens ? usage.saved_tokens / usage.raw_tokens * 100 : 0;
  $('#usedTokenCount').textContent = compactNumber(usage.context_tokens);
  $('#requestLabel').textContent = `${compactNumber(usage.requests)} context requests`;
  $('#rawTokenCount').textContent = compactNumber(usage.raw_tokens);
  $('#optimizedTokenCount').textContent = compactNumber(usage.context_tokens);
  $('#rawBar').style.width = usage.raw_tokens ? '100%' : '0%';
  $('#optimizedBar').style.width = usage.raw_tokens ? `${Math.min(100, usage.context_tokens / usage.raw_tokens * 100)}%` : '0%';
  $('#savingValue').innerHTML = `${savedPercent.toFixed(2)}<small>%</small>`;
  $('#tokenLabel').textContent = `${compactNumber(usage.saved_tokens)} estimated tokens saved`;
  $('#repoHint').textContent = `${compactNumber(stats.files)} files · ${compactNumber(stats.symbols)} symbols · ${stats.scan_seconds == null ? 'scan time unavailable' : `${Number(stats.scan_seconds).toFixed(2)}s scan`}`;
  $('#footerRepo').textContent = $('#repoPath').textContent;
  $('#repoState').textContent = 'LIVE ANALYSIS';
  $('#graphEmpty').hidden = stats.nodes > 0;
  renderLanguages(stats.languages);
  await Promise.all([loadGraph(), loadDiagnostics()]);
}
function renderLanguages(languages=[]) {
  const target = $('#languageLegend'); target.replaceChildren();
  if (!languages.length) { target.innerHTML = '<span class="muted">No supported source files</span>'; return; }
  for (const [index, item] of languages.slice(0, 6).entries()) {
    const row = document.createElement('div'); row.className = 'language-item';
    const dot = document.createElement('i'); dot.style.setProperty('--color', languageColor(index));
    const name = document.createElement('span'); name.textContent = item.name;
    const count = document.createElement('b'); count.textContent = compactNumber(item.files);
    row.append(dot, name, count); target.append(row);
  }
}
async function loadDiagnostics() {
  try {
    const items = await api('/api/diagnostics'); const target = $('#diagnosticsList'); target.replaceChildren();
    if (!items.length) { const empty = document.createElement('div'); empty.className='empty-inline'; empty.textContent='✓ No indexing diagnostics to report.'; target.append(empty); return; }
    for (const item of items.slice(0, 12)) {
      const row = document.createElement('div'); row.className='diagnostic-row';
      const severity = document.createElement('span'); severity.className=`diagnostic-severity ${item.severity === 'error' ? 'error' : ''}`; severity.textContent=item.severity || 'info';
      const copy = document.createElement('span'); copy.textContent=item.message;
      row.append(severity, copy);
      if (item.file_path) { const path=document.createElement('span'); path.className='diagnostic-path'; path.textContent=item.file_path; row.append(path); }
      target.append(row);
    }
  } catch (error) { console.warn(error); }
}
async function loadGraph() {
  try { state.graph = await api('/api/graph'); drawGraph(); }
  catch (error) { if (error.message.includes('Select') || error.message.includes('not been scanned')) return; throw error; }
}
function makeSvg(tag, attrs={}) {
  const el=document.createElementNS(svgNS,tag); for(const [key,value] of Object.entries(attrs)) el.setAttribute(key,String(value)); return el;
}
function hashText(text) { let hash=2166136261; for(let i=0;i<text.length;i++) hash=Math.imul(hash^text.charCodeAt(i),16777619); return hash>>>0; }
function graphNodes() {
  const nodes=state.graph?.nodes || []; const width=1000,height=560; const map=new Map();
  const files=nodes.filter(node=>node.type==='file'); const symbols=nodes.filter(node=>node.type!=='file');
  const layout=(list,rx,ry,start=0)=>list.forEach((node,index)=>{ const angle=((index+start)*2.3999632297)+(hashText(node.id||node.label)%40)/100; const radius=0.25+0.72*Math.sqrt((index+1)/(list.length+1)); node._x=width/2+Math.cos(angle)*rx*radius; node._y=height/2+Math.sin(angle)*ry*radius; map.set(node.id,node); });
  layout(files,390,205,0); layout(symbols,275,155,files.length*.31);
  return map;
}
function drawGraph() {
  const data=state.graph; const group=$('#graphViewport'); group.replaceChildren(); if(!data) return;
  const all=graphNodes(); const needle=$('#graphFilter').value.trim().toLowerCase();
  const visible=new Set();
  for(const node of data.nodes){ if(!needle || `${node.label} ${node.type}`.toLowerCase().includes(needle)) visible.add(node.id); }
  if(needle){ for(const edge of data.edges){ if(visible.has(edge.source)||visible.has(edge.target)){visible.add(edge.source);visible.add(edge.target);} } }
  const edgesGroup=makeSvg('g',{class:'edges'}); const nodesGroup=makeSvg('g',{class:'nodes'});
  for(const edge of data.edges){ if(!visible.has(edge.source)||!visible.has(edge.target)) continue; const source=all.get(edge.source), target=all.get(edge.target); if(!source||!target) continue;
    const line=makeSvg('line',{x1:source._x,y1:source._y,x2:target._x,y2:target._y,stroke:edge.type==='depends_on'?'#4d8c79':'#334250','stroke-width':edge.type==='depends_on'?1.3:.75,opacity:edge.type==='depends_on'?.48:.3}); edgesGroup.append(line);
  }
  for(const node of data.nodes){ if(!visible.has(node.id)) continue; const color=palette[node.type]||palette.default; const radius=node.type==='file'?6.2:node.type==='module'?4.4:3.3;
    const g=makeSvg('g',{class:'graph-node',transform:`translate(${node._x} ${node._y})`,tabindex:0,role:'button','aria-label':`${node.type}: ${node.label}`,'data-id':node.id});
    const circle=makeSvg('circle',{r:radius,fill:color,stroke:node.type==='file'?'#c9fff0':'#101922','stroke-width':node.type==='file'?1.1:.6,filter:node.type==='file'?'url(#glow)':''});
    const label=makeSvg('text',{x:radius+5,y:3,fill:node.type==='file'?'#c1d1d8':'#8293a2','font-size':node.type==='file'?9:7.2,'font-family':'DM Mono, monospace'}); label.textContent=String(node.label||'').slice(0,28);
    g.append(circle,label); g.addEventListener('click',()=>{if(node.type==='file') openSource(node.label);});
    g.addEventListener('pointerdown',event=>{event.stopPropagation();state.dragging={id:node.id,element:g,node};g.setPointerCapture(event.pointerId);});
    g.addEventListener('pointermove',event=>{if(!state.dragging||state.dragging.id!==node.id)return; const point=svgPoint(event); node._x=point.x;node._y=point.y;g.setAttribute('transform',`translate(${point.x} ${point.y})`);drawGraph();});
    g.addEventListener('pointerup',()=>{state.dragging=null;});
    nodesGroup.append(g);
  }
  group.append(edgesGroup,nodesGroup); applyTransform();
  $('#graphNodeLabel').textContent=`${visible.size} shown`;
  $('#graphEmpty').hidden=visible.size>0;
}
function svgPoint(event){const svg=$('#graphSvg'),point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;return point.matrixTransform(svg.getScreenCTM().inverse());}
function applyTransform(){ $('#graphViewport').setAttribute('transform',`translate(${state.tx} ${state.ty}) scale(${state.scale})`); }
function zoom(amount){state.scale=Math.min(2.8,Math.max(.45,state.scale*amount));applyTransform();}
function openSource(path){api(`/api/file?path=${encodeURIComponent(path)}`).then(data=>{ $('#sourcePath').textContent=data.path; $('#sourceCode').textContent=data.lines.map((line,index)=>`${String(data.start+index).padStart(4,' ')}  ${line}`).join('\n');$('#sourceDialog').showModal(); }).catch(error=>showToast(error.message));}
function renderResults(data,title='Repository context'){
  const panel=$('#resultPanel');panel.hidden=false;$('#resultTitle').textContent=title;
  const raw=Number(data.raw_tokens||0), compact=Number(data.context_tokens||0), savingsKnown=data.context_savings_percent!==null&&data.context_savings_percent!==undefined&&raw>0, saved=savingsKnown?Number(data.context_savings_percent):0;
  $('#resultMetric').textContent=savingsKnown?`${compactNumber(raw)} → ${compactNumber(compact)} TOKENS  /  ${saved.toFixed(2)}% EST. SAVED`:`${compactNumber(raw)} BASELINE TOKENS  /  NO MATCH - NOT COUNTED`;
  $('#resultFiles').textContent=`${(data.files||[]).length} relevant file${(data.files||[]).length===1?'':'s'}`;
  const body=$('#resultBody');body.textContent=data.text||data.context||'No matching indexed source was found. Try different terms or rescan the repository.';
  const citations=$('#citationList');citations.replaceChildren();
  for(const ref of (data.references||[])){const button=document.createElement('button');button.className='citation-chip';button.type='button';button.innerHTML=`<span></span><small></small>`;button.children[0].textContent=ref.path;button.children[1].textContent=(ref.symbols||[]).slice(0,2).map(s=>`${s.name}:${s.line}`).join(' · ')||'open source';button.addEventListener('click',()=>openSource(ref.path));citations.append(button);}
  if(savingsKnown){$('#savingValue').innerHTML=`${saved.toFixed(2)}<small>%</small>`;$('#tokenLabel').textContent=`${compactNumber(raw)} raw → ${compactNumber(compact)} retrieved`;}
  $('#optimizedTokenCount').textContent=compactNumber(compact);$('#rawTokenCount').textContent=compactNumber(raw);
  $('#rawBar').style.width=raw?'100%':'0%';$('#optimizedBar').style.width=raw?`${Math.min(100,compact/raw*100)}%`:'0%';
  $('#tokenNote').textContent=`This query: ${compactNumber(raw)} full-source estimate → ${compactNumber(compact)} prepared context. Totals are local estimates in .braingraph/usage.json, not provider tokens or billing; empty retrievals are not counted as savings.`;
  if (data.cumulative_usage) {
    const usage=data.cumulative_usage;
    const savedPercent=usage.raw_tokens?usage.saved_tokens/usage.raw_tokens*100:0;
    $('#usedTokenCount').textContent=compactNumber(usage.context_tokens);
    $('#requestLabel').textContent=`${compactNumber(usage.requests)} context requests`;
    $('#tokenLabel').textContent=`${compactNumber(usage.saved_tokens)} estimated tokens saved`;
    $('#savingValue').innerHTML=`${savedPercent.toFixed(2)}<small>%</small>`;
    $('#rawTokenCount').textContent=compactNumber(usage.raw_tokens);
    $('#optimizedTokenCount').textContent=compactNumber(usage.context_tokens);
    $('#rawBar').style.width=usage.raw_tokens?'100%':'0%';
    $('#optimizedBar').style.width=usage.raw_tokens?`${Math.min(100,usage.context_tokens/usage.raw_tokens*100)}%`:'0%';
  }
  panel.scrollIntoView({behavior:'smooth',block:'nearest'});
}
async function runQuery(text, action='ask'){
  if(!text||text.trim().length<2){showToast('Enter a question with at least two characters.');return;}
  $('#askButton').disabled=true;
  try{
    if(action==='ask'&&!state.aiConfigured){const result=await api('/api/query',{method:'POST',body:JSON.stringify({query:text,limit:8})});renderResults(result,'Retrieved code context');}
    else {const result=await api('/api/action',{method:'POST',body:JSON.stringify({action,query:text})});
      if(!result.available){renderResults({...result.context,text:`AI is not configured. ${result.message}\n\nRetrieved repository context:\n\n${result.context.context||'(No matching indexed source found.)'}`},'AI provider unavailable / local evidence');}
      else if(result.error){renderResults({...result.context,text:`AI request failed. ${result.error}\n\nRetrieved repository context:\n\n${result.context.context||'(No matching indexed source found.)'}`},'Provider error / local evidence');}
      else renderResults({...result.context,text:result.text},'AI analysis with source context');
    }
  }catch(error){showToast(error.message);}finally{$('#askButton').disabled=false;}
}
function escapeHtml(text){return String(text).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));}

$('#questionForm').addEventListener('submit',event=>{event.preventDefault();runQuery($('#questionInput').value,'ask');});
for(const button of document.querySelectorAll('.action-card'))button.addEventListener('click',()=>{
  const action=button.dataset.action;const question=$('#questionInput').value.trim()||({explain:'Explain the project structure and main execution flow',bugs:'Find possible bugs and fragile error handling',architecture:'Summarize the repository architecture and key module relationships',refactor:'Suggest focused refactoring opportunities'}[action]||'Explain the relevant code');
  $('#questionInput').value=question;runQuery(question,action);
});
for(const button of document.querySelectorAll('[data-question]'))button.addEventListener('click',()=>{$('#questionInput').value=button.dataset.question;$('#questionInput').focus();});
$('#graphFilter').addEventListener('input',drawGraph);
$('#fitGraph').addEventListener('click',()=>{state.scale=1;state.tx=0;state.ty=0;drawGraph();});
$('#zoomIn').addEventListener('click',()=>zoom(1.2));$('#zoomOut').addEventListener('click',()=>zoom(.83));
$('#graphSvg').addEventListener('wheel',event=>{event.preventDefault();zoom(event.deltaY<0?1.1:.91);},{passive:false});
$('#graphSvg').addEventListener('pointerdown',event=>{if(event.target.closest('.graph-node'))return;state.pan={x:event.clientX,y:event.clientY,tx:state.tx,ty:state.ty};});
$('#graphSvg').addEventListener('pointermove',event=>{if(!state.pan)return;state.tx=state.pan.tx+event.clientX-state.pan.x;state.ty=state.pan.ty+event.clientY-state.pan.y;applyTransform();});
window.addEventListener('pointerup',()=>{state.pan=null;state.dragging=null;});
$('#clearResult').addEventListener('click',()=>$('#resultPanel').hidden=true);
$('#closeSource').addEventListener('click',()=>$('#sourceDialog').close());
$('#sourceDialog').addEventListener('click',event=>{if(event.target===$('#sourceDialog'))$('#sourceDialog').close();});
loadStatus().catch(error=>showToast(error.message));
