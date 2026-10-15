/* Just Sing v42 - fix browse, fix delete with icon modal, v1.7 chorus */
const DEFAULT_STYLE = 'warm-acoustic';
let selectedFile = null;
let currentJobId = null;
let pollTimer = null;
let recChunks = [], mediaRecorder = null, recStartTime = null, recTimerInterval = null;
let audioCtx = null, vocalBuffer = null, accBuffer = null, vocalGainNode = null, accGainNode = null, masterGainNode = null, isMixerReady = false;
let recMode = 'audio', videoStream = null, videoRecorder = null, videoChunks = [], videoStartTime = null, videoTimerInterval = null, facingMode = 'user';
let isPlaying = false;
let pendingDeleteJobId = null, pendingDeleteMode = 'single'; // single, current, clearAll

const el = (id) => document.getElementById(id);
const log = (m) => { console.log(m); const d=el('debugLog'); if(d){ d.textContent='['+new Date().toLocaleTimeString()+'] '+m+'\n'+d.textContent.slice(0,3000);} };
const showError = (msg) => { const b=el('errorBox'); if(!b)return; b.textContent=msg; b.classList.remove('hidden'); log('ERR '+msg); };
const hideError = () => { const b=el('errorBox'); if(b)b.classList.add('hidden'); };
function icon(name,cls){ return `<svg class="${cls||'w-4 h-4'}"><use href="#i-${name}"/></svg>`; }

function initLiveBars(){
 const c=el('liveBars'); if(!c)return; c.innerHTML=''; for(let i=0;i<16;i++){ const b=document.createElement('div'); b.className='w-[3px] bg-[#e8dcc6] rounded-full'; b.style.height='5px'; c.appendChild(b); }
}

function setFile(file, nameHint){
 if(!file){ log('setFile null'); return; }
 selectedFile = file;
 log(`File set: ${nameHint||file.name} size=${file.size} type=${file.type}`);
 el('fileInfo').classList.remove('hidden');
 el('fileName').textContent = nameHint || file.name || 'recording.webm';
 el('fileMeta').textContent = `${(file.size/1024/1024).toFixed(2)} MB · ${file.type||'audio'}`;
 const genBtn = el('generateBtn');
 genBtn.disabled = false;
 genBtn.className = 'mt-4 w-full h-[52px] rounded-full bg-zinc-900 text-white font-medium text-[15px] hover:bg-black transition flex items-center justify-center gap-2 shadow-[0_8px_24px_rgba(0,0,0,0.18)] cursor-pointer';
 genBtn.innerHTML = `<span>Create song</span><span class="w-6 h-6 rounded-full bg-white/15 flex items-center justify-center">${icon('arrow','w-3.5 h-3.5')}</span>`;
 hideError();
}

function clearFile(){
 selectedFile = null;
 const fi=el('fileInput'); if(fi)fi.value='';
 const fileInfo=el('fileInfo'); if(fileInfo)fileInfo.classList.add('hidden');
 const genBtn=el('generateBtn'); if(genBtn){ genBtn.disabled=true; genBtn.className='mt-4 w-full h-[52px] rounded-full bg-[#fdf8ef] border border-[#e8dcc6] text-zinc-400 font-medium text-[15px] cursor-not-allowed flex items-center justify-center gap-2'; genBtn.innerHTML='<span>Add audio to continue</span>'; }
 log('File cleared');
}

async function uploadAndGenerate(){
 if(!selectedFile){ showError('No file selected. Add audio first.'); return; }
 hideError();
 const fd = new FormData();
 const fileName = selectedFile.name || `upload_${Date.now()}.webm`;
 fd.append('file', selectedFile, fileName);
 fd.append('style', DEFAULT_STYLE);
 const pc=el('progressCard'); if(pc)pc.classList.remove('hidden');
 const rv=el('resultView'); if(rv)rv.classList.add('hidden');
 const cv=el('createView'); if(cv)cv.classList.remove('hidden');
 const pb=el('progressBar'); if(pb)pb.style.width='5%';
 const pct=el('progressPct'); if(pct)pct.textContent='5%';
 const pm=el('progressMsg'); if(pm)pm.textContent='Uploading...';
 log(`Uploading ${fileName} style ${DEFAULT_STYLE} size ${selectedFile.size}`);
 try{
  const res = await fetch('/api/upload', { method:'POST', body:fd });
  const text = await res.text();
  log(`Upload ${res.status}: ${text.slice(0,500)}`);
  if(!res.ok) throw new Error(`Upload failed ${res.status}: ${text.slice(0,400)}`);
  const data = JSON.parse(text);
  currentJobId = data.job_id;
  if(!currentJobId) throw new Error('No job_id');
  if(pm)pm.textContent='Queued... '+currentJobId.slice(0,8);
  pollJob(currentJobId);
 }catch(e){
  showError('Upload failed: '+e.message);
  const pm2=el('progressMsg'); if(pm2)pm2.textContent='Upload failed: '+e.message;
 }
}

function pollJob(jobId){
 if(pollTimer) clearInterval(pollTimer);
 const poll = async ()=>{
  try{
   const res = await fetch(`/api/jobs/${jobId}`);
   if(!res.ok) throw new Error('job not found '+res.status);
   const job = await res.json();
   const pct = job.progress||0;
   const pb=el('progressBar'); if(pb)pb.style.width=`${pct}%`;
   const pctEl=el('progressPct'); if(pctEl)pctEl.textContent=`${pct}%`;
   const pm=el('progressMsg'); if(pm)pm.textContent=job.message||job.status;
   if(job.status==='completed'){ clearInterval(pollTimer); pollTimer=null; showResult(job); loadJobs(); }
   else if(job.status==='failed'){ clearInterval(pollTimer); pollTimer=null; showError('Generation failed: '+(job.error||job.message)); const pm2=el('progressMsg'); if(pm2)pm2.textContent='Failed: '+(job.error||job.message); }
  }catch(e){ log('Poll error: '+e.message); }
 };
 poll(); pollTimer=setInterval(poll,1200);
}

function generateWaveformBars(count,color){
 let html=''; for(let i=0;i<count;i++){ const h=8+Math.abs(Math.sin(i*0.2+Math.random()*0.5))*22+Math.random()*8; const o=0.7+Math.random()*0.3; html+=`<span class="wave-bar" style="height:${h}px;background:${color};opacity:${o}"></span>`; } return html;
}
function renderWaveforms(){
 const v=el('vocalWaveform'), t=el('trackWaveform');
 if(v)v.innerHTML=generateWaveformBars(100,'#c94a1a');
 if(t)t.innerHTML=generateWaveformBars(100,'#2d5a4c');
}

async function initVolumeMixer(vocalUrl, accUrl){
 log('Init mixer v42');
 const status=el('customMixStatus'); if(status)status.textContent='Loading...';
 try{
  if(!audioCtx) audioCtx=new (window.AudioContext||window.webkitAudioContext)();
  const [vr,ar]=await Promise.all([fetch(vocalUrl), fetch(accUrl)]);
  const [vb,ab]=await Promise.all([vr.arrayBuffer(), ar.arrayBuffer()]);
  const [vBuf,aBuf]=await Promise.all([audioCtx.decodeAudioData(vb.slice(0)), audioCtx.decodeAudioData(ab.slice(0))]);
  vocalBuffer=vBuf; accBuffer=aBuf;
  vocalGainNode=audioCtx.createGain(); accGainNode=audioCtx.createGain(); masterGainNode=audioCtx.createGain();
  vocalGainNode.gain.value=1.0; accGainNode.gain.value=0.35; masterGainNode.gain.value=1.0;
  vocalGainNode.connect(masterGainNode); accGainNode.connect(masterGainNode); masterGainNode.connect(audioCtx.destination);
  isMixerReady=true;
  if(status)status.textContent='Mixer ready';
  setupMixerSliders(); await renderMixedPreview(); renderWaveforms();
 }catch(e){ log('Mixer failed: '+e.message); if(status)status.textContent='Mixer failed: '+e.message; }
}

function setupMixerSliders(){
 const vs=el('vocalGainSlider'), as=el('accGainSlider'), ms=el('masterGainSlider');
 const vl=el('vocalGainLabel'), al=el('accGainLabel'), ml=el('masterGainLabel');
 if(!vs){ log('sliders not found'); return; }
 const updV=()=>{ const v=parseInt(vs.value); if(vl)vl.textContent=v+'%'; if(vocalGainNode)vocalGainNode.gain.value=v/100; const va=el('vocalAudio'); if(va)va.volume=Math.min(1,v/100); debounceRenderPreview(); };
 const updA=()=>{ const v=parseInt(as.value); if(al)al.textContent=v+'%'; if(accGainNode)accGainNode.gain.value=v/100; const aa=el('accAudio'); if(aa)aa.volume=Math.min(1,v/100*1.5); debounceRenderPreview(); };
 const updM=()=>{ const v=parseInt(ms.value); if(ml)ml.textContent=v+'%'; if(masterGainNode)masterGainNode.gain.value=v/100; const fa=el('finalAudio'); if(fa)fa.volume=Math.min(1,v/100); debounceRenderPreview(); };
 vs.addEventListener('input',updV); as.addEventListener('input',updA); ms.addEventListener('input',updM);
 if(vl)vl.textContent=vs.value+'%'; if(al)al.textContent=as.value+'%'; if(ml)ml.textContent=ms.value+'%';
 log('Mixer sliders ready');
}
let renderDebounceTimer=null, serverMixDebounceTimer=null;
function debounceRenderPreview(){
 if(renderDebounceTimer)clearTimeout(renderDebounceTimer);
 renderDebounceTimer=setTimeout(()=>{ renderMixedPreview(); },250);
 if(serverMixDebounceTimer)clearTimeout(serverMixDebounceTimer);
 serverMixDebounceTimer=setTimeout(()=>{ if(currentJobId){ log('Auto server mix...'); renderCustomMixOnServer(); } },1000);
}
async function renderMixedPreview(){
 if(!isMixerReady||!vocalBuffer||!accBuffer||!audioCtx)return;
 const vg=el('vocalGainSlider')?parseInt(el('vocalGainSlider').value)/100:1.0;
 const ag=el('accGainSlider')?parseInt(el('accGainSlider').value)/100:0.35;
 const mg=el('masterGainSlider')?parseInt(el('masterGainSlider').value)/100:1.0;
 try{
  const duration=Math.max(vocalBuffer.duration, accBuffer.duration);
  const offlineCtx=new OfflineAudioContext(2, Math.ceil(duration*audioCtx.sampleRate), audioCtx.sampleRate);
  const vso=offlineCtx.createBufferSource(); vso.buffer=vocalBuffer; const vgn=offlineCtx.createGain(); vgn.gain.value=vg; vso.connect(vgn);
  const aso=offlineCtx.createBufferSource(); aso.buffer=accBuffer; const agn=offlineCtx.createGain(); agn.gain.value=ag; aso.connect(agn);
  const mgn=offlineCtx.createGain(); mgn.gain.value=mg; vgn.connect(mgn); agn.connect(mgn); mgn.connect(offlineCtx.destination);
  vso.start(0); aso.start(0);
  const rendered=await offlineCtx.startRendering();
  const blob=bufferToWavBlob(rendered);
  const url=URL.createObjectURL(blob);
  const mp=el('mixedPreviewAudio'); if(mp)mp.src=url;
  const fa=el('finalAudio'); if(fa){ fa.src=url; fa.load(); const dlMp3=el('dlMp3'); if(dlMp3)dlMp3.href=url; const dlWav=el('dlWav'); if(dlWav)dlWav.href=url; log(`Slider -> finalAudio vocal ${vg.toFixed(2)} track ${ag.toFixed(2)} master ${mg.toFixed(2)}`); }
 }catch(e){ log('render preview failed: '+e.message); }
}
function bufferToWavBlob(buffer){
 const numChannels=buffer.numberOfChannels, sampleRate=buffer.sampleRate, length=buffer.length;
 const interleaved=new Float32Array(length*numChannels);
 for(let ch=0;ch<numChannels;ch++){ const cd=buffer.getChannelData(ch); for(let i=0;i<length;i++){ interleaved[i*numChannels+ch]=cd[i]; } }
 const wavLength=44+interleaved.length*2, wavBuffer=new ArrayBuffer(wavLength), view=new DataView(wavBuffer);
 const ws=(o,s)=>{ for(let i=0;i<s.length;i++) view.setUint8(o+i,s.charCodeAt(i)); };
 ws(0,'RIFF'); view.setUint32(4,wavLength-8,true); ws(8,'WAVE'); ws(12,'fmt '); view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,numChannels,true); view.setUint32(24,sampleRate,true); view.setUint32(28,sampleRate*numChannels*2,true); view.setUint16(32,numChannels*2,true); view.setUint16(34,16,true); ws(36,'data'); view.setUint32(40,interleaved.length*2,true);
 let off=44; for(let i=0;i<interleaved.length;i++){ const s=Math.max(-1,Math.min(1,interleaved[i])); view.setInt16(off,s<0?s*0x8000:s*0x7FFF,true); off+=2; }
 return new Blob([view],{type:'audio/wav'});
}
async function renderCustomMixOnServer(){
 if(!currentJobId)return;
 const vg=el('vocalGainSlider')?parseInt(el('vocalGainSlider').value)/100:1.0, ag=el('accGainSlider')?parseInt(el('accGainSlider').value)/100:0.35, mg=el('masterGainSlider')?parseInt(el('masterGainSlider').value)/100:1.0;
 const status=el('customMixStatus'), resultDiv=el('customMixResult');
 if(status)status.textContent='Rendering...';
 try{
  const fd=new FormData(); fd.append('vocal_gain',vg.toString()); fd.append('acc_gain',ag.toString()); fd.append('master_gain',mg.toString());
  const res=await fetch(`/api/jobs/${currentJobId}/mix-custom`,{method:'POST',body:fd});
  const text=await res.text(); const data=JSON.parse(text);
  if(resultDiv)resultDiv.classList.remove('hidden');
  el('customMixAudio').src=data.files.mp3||data.files.wav;
  el('dlCustomMp3').href=data.files.mp3||data.files.wav;
  el('dlCustomWav').href=data.files.wav;
  if(status)status.textContent='Ready';
 }catch(e){ if(status)status.textContent='Failed: '+e.message; }
}

function showResult(job){
 const cv=el('createView'), rv=el('resultView');
 if(cv)cv.classList.add('hidden'); if(rv)rv.classList.remove('hidden');
 const files=job.files||{};
 const meta=el('resultMeta'); if(meta)meta.textContent=`${job.analysis?.key||''} · ${job.analysis?.bpm||''} BPM · v1.7 chorus`;
 if(files.mp3)el('finalAudio').src=files.mp3;
 if(files.mp3){ el('dlMp3').href=files.mp3; const dlBtn=el('downloadBtn'); if(dlBtn)dlBtn.onclick=()=>{ const vf=files.video||files.final_video||files.video_mp4; const url=vf||files.mp3; const a=document.createElement('a'); a.href=url; a.download=`justsing_${currentJobId}.${vf?'mp4':'mp3'}`; a.click(); }; }
 if(files.wav)el('dlWav').href=files.wav;
 if(files.vocal)el('vocalAudio').src=files.vocal;
 if(files.accompaniment)el('accAudio').src=files.accompaniment;
 const videoBox=el('videoResultBox'), finalVideo=el('finalVideo'), dlVideo=el('dlVideo');
 const videoFile=files.video||files.final_video||files.video_mp4;
 if(videoFile&&videoBox&&finalVideo){ videoBox.classList.remove('hidden'); finalVideo.src=videoFile; if(dlVideo)dlVideo.href=videoFile; }
 else if(videoBox)videoBox.classList.add('hidden');
 if(files.vocal&&files.accompaniment){ setTimeout(()=>{ initVolumeMixer(files.vocal, files.accompaniment); },400); } else { renderWaveforms(); }
 const finalAudio=el('finalAudio'), playPauseBtn=el('playPauseBtn'), curEl=el('currentTime'), totEl=el('totalTime');
 if(finalAudio){
  finalAudio.ontimeupdate=()=>{ if(curEl)curEl.textContent=formatTime(finalAudio.currentTime); if(totEl)totEl.textContent=formatTime(finalAudio.duration||0); };
  finalAudio.onended=()=>{ isPlaying=false; if(playPauseBtn)playPauseBtn.innerHTML=`${icon('play','w-3.5 h-3.5')}Play`; };
 }
 if(playPauseBtn&&finalAudio){
  playPauseBtn.onclick=()=>{ if(isPlaying){ finalAudio.pause(); playPauseBtn.innerHTML=`${icon('play','w-3.5 h-3.5')}Play`; isPlaying=false; } else { finalAudio.play(); playPauseBtn.innerHTML=`${icon('pause','w-3.5 h-3.5')}Pause`; isPlaying=true; } };
 }
 window.scrollTo({top:0,behavior:'smooth'});
}
function formatTime(sec){ if(!sec||isNaN(sec))return '00:00'; const m=Math.floor(sec/60), s=Math.floor(sec%60); return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`; }

// --- Delete Modal with Icon (no alert) ---
function openDeleteModal(jobId, mode='single'){
 pendingDeleteJobId = jobId;
 pendingDeleteMode = mode;
 const modal = el('deleteModal');
 const title = el('deleteModalTitle');
 const msg = el('deleteModalMsg');
 const confirmBtn = el('deleteModalConfirm');
 if(!modal) return;
 if(mode==='clearAll'){
  if(title) title.textContent='Clear all songs?';
  if(msg) msg.textContent='This will permanently delete all your songs. This action cannot be undone.';
  if(confirmBtn) confirmBtn.innerHTML=`${icon('trash','w-4 h-4')} Clear all`;
 } else {
  const shortId = jobId ? jobId.slice(0,8) : '';
  if(title) title.textContent='Delete song?';
  if(msg) msg.textContent= shortId ? `Delete song ${shortId}? This will permanently remove it.` : 'This will permanently delete the song.';
  if(confirmBtn) confirmBtn.innerHTML=`${icon('trash','w-4 h-4')} Delete`;
 }
 modal.classList.remove('hidden');
 document.body.style.overflow='hidden';
 log(`Open delete modal mode=${mode} job=${jobId||'all'}`);
}
function closeDeleteModal(){
 const modal = el('deleteModal');
 if(modal) modal.classList.add('hidden');
 document.body.style.overflow='';
 pendingDeleteJobId = null;
 pendingDeleteMode = 'single';
}
async function confirmDelete(){
 const mode = pendingDeleteMode;
 const jobId = pendingDeleteJobId;
 closeDeleteModal();
 if(mode==='clearAll'){
  await clearAllJobsConfirmed();
 } else if(jobId){
  await deleteJobConfirmed(jobId);
 }
}
async function deleteJobConfirmed(jobId){
 if(!jobId) return;
 log(`Deleting job ${jobId}`);
 try{
  const res = await fetch(`/api/jobs/${jobId}`,{method:'DELETE'});
  if(!res.ok) throw new Error(await res.text());
  if(currentJobId===jobId){ currentJobId=null; el('resultView')?.classList.add('hidden'); el('createView')?.classList.remove('hidden'); }
  await loadJobs();
  log(`Deleted ${jobId}`);
 }catch(e){ showError('Delete failed: '+e.message); }
}
async function clearAllJobsConfirmed(){
 try{
  const res=await fetch('/api/jobs?limit=100'); const data=await res.json(); const jobs=data.jobs||[];
  if(jobs.length===0){ showError('No songs to clear'); return; }
  for(const j of jobs){ try{ await fetch(`/api/jobs/${j.job_id}`,{method:'DELETE'}); }catch{} }
  currentJobId=null; el('resultView')?.classList.add('hidden'); el('createView')?.classList.remove('hidden'); el('progressCard')?.classList.add('hidden'); await loadJobs();
  log('Cleared all');
 }catch(e){ showError('Clear failed: '+e.message); }
}

async function loadJobs(){
 try{
  const res=await fetch('/api/jobs?limit=20'); const data=await res.json();
  const list=el('jobsList'), empty=el('emptyState'), jc=el('jobsCount'), wc=el('workspaceCount');
  const count=data.jobs?data.jobs.length:0;
  if(jc){ jc.textContent=count; jc.classList.toggle('hidden',count===0); }
  if(wc)wc.textContent=count+(count===1?' song':' songs');
  if(!data.jobs||data.jobs.length===0){ if(empty)empty.style.display='flex'; if(list)list.innerHTML=''; return; }
  if(empty)empty.style.display='none'; if(!list)return; list.innerHTML='';
  data.jobs.forEach(j=>{
   const div=document.createElement('div');
   div.className='group flex items-center justify-between p-3 rounded-[12px] bg-[#fdf8ef] border border-[#e8dcc6] hover:bg-white cursor-pointer transition text-[13px]';
   const dot=j.status==='completed'?'bg-emerald-500':j.status==='failed'?'bg-red-500':'bg-amber-500';
   const title=j.original_filename||j.job_id.slice(0,8);
   const safeTitle=title.replace(/</g,'&lt;').slice(0,24);
   div.innerHTML=`<div class="flex items-center gap-2 min-w-0 flex-1"><span class="w-2 h-2 rounded-full ${dot} shrink-0"></span><span class="font-medium truncate">${safeTitle}</span><span class="hidden sm:inline mono text-[11px] text-zinc-500">${j.analysis?.key||''} ${j.progress||0}%</span></div><button type="button" class="deleteBtn w-7 h-7 rounded-full bg-white border border-[#e8dcc6] flex items-center justify-center hover:bg-red-50 hover:border-red-200 hover:text-red-600 transition shrink-0" data-job="${j.job_id}" aria-label="Delete">${icon('trash','w-3.5 h-3.5')}</button>`;
   div.onclick=(e)=>{ if(e.target.closest('.deleteBtn'))return; currentJobId=j.job_id; el('progressCard')?.classList.remove('hidden'); if(j.status==='completed')showResult(j); else { el('createView')?.classList.remove('hidden'); el('resultView')?.classList.add('hidden'); pollJob(j.job_id); } window.scrollTo({top:0,behavior:'smooth'}); };
   const delBtn=div.querySelector('.deleteBtn');
   if(delBtn){
    delBtn.onclick=(e)=>{
     e.preventDefault(); e.stopPropagation();
     log(`Delete btn clicked ${j.job_id}`);
     openDeleteModal(j.job_id,'single');
    };
   }
   list.appendChild(div);
  });
 }catch(e){ log('loadJobs failed: '+e.message); }
}

async function toggleRecord(){
 const btn=el('recBtn'), status=el('recStatus');
 if(mediaRecorder&&mediaRecorder.state==='recording'){ mediaRecorder.stop(); if(btn)btn.textContent='●'; if(status)status.textContent='PROCESSING'; clearInterval(recTimerInterval); return; }
 if(!navigator.mediaDevices?.getUserMedia){ showError('Recording not supported'); return; }
 try{
  const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true}});
  recChunks=[]; let mime='audio/webm'; if(MediaRecorder.isTypeSupported('audio/webm;codecs=opus'))mime='audio/webm;codecs=opus';
  mediaRecorder=new MediaRecorder(stream,{mimeType:mime});
  mediaRecorder.ondataavailable=e=>{ if(e.data.size>0)recChunks.push(e.data); };
  mediaRecorder.onstop=()=>{ const blob=new Blob(recChunks,{type:mediaRecorder.mimeType}); const url=URL.createObjectURL(blob); const p=el('recPreview'); if(p){ p.src=url; p.classList.remove('hidden'); } const file=new File([blob],`recording_${Date.now()}.webm`,{type:blob.type}); setFile(file,file.name); if(status)status.textContent='READY'; stream.getTracks().forEach(t=>t.stop()); };
  mediaRecorder.start(100); recStartTime=Date.now();
  if(btn)btn.textContent='■'; if(status){ status.textContent='REC'; status.className='mono text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 border border-red-200'; }
  recTimerInterval=setInterval(()=>{ const e=Math.floor((Date.now()-recStartTime)/1000); const mm=String(Math.floor(e/60)).padStart(2,'0'), ss=String(e%60).padStart(2,'0'); const rt=el('recTimer'); if(rt)rt.textContent=`${mm}:${ss}`; },400);
  try{
   const ac=new (window.AudioContext||window.webkitAudioContext)(), src=ac.createMediaStreamSource(stream), an=ac.createAnalyser(); an.fftSize=128; src.connect(an);
   const da=new Uint8Array(an.frequencyBinCount), bc=el('liveBars'), bars=bc?bc.children:[];
   const loop=()=>{ if(!mediaRecorder||mediaRecorder.state!=='recording'){ try{ac.close();}catch{} return; } an.getByteFrequencyData(da); for(let i=0;i<bars.length;i++){ const v=da[i*2]/255; bars[i].style.height=`${4+v*18}px`; bars[i].className='w-[3px] bg-[#e85d26] rounded-full'; } requestAnimationFrame(loop); }; loop();
  }catch{}
 }catch(e){ showError('Mic error: '+e.message); if(status)status.textContent='BLOCKED'; }
}

async function startVideoPreview(){
 const videoEl=el('videoPreview'), ph=el('videoPreviewPlaceholder'), status=el('videoRecStatus');
 if(!videoEl)return;
 try{
  if(videoStream)videoStream.getTracks().forEach(t=>t.stop());
  const constraints={video:{facingMode:facingMode,width:{ideal:1280},height:{ideal:720}},audio:true};
  videoStream=await navigator.mediaDevices.getUserMedia(constraints);
  videoEl.srcObject=videoStream;
  if(ph)ph.classList.add('hidden');
  if(status)status.textContent='READY';
  log(`Video preview ${facingMode}`);
 }catch(e){ showError('Camera error: '+e.message); if(status)status.textContent='BLOCKED'; }
}
function stopVideoPreview(){ if(videoStream){ videoStream.getTracks().forEach(t=>t.stop()); videoStream=null; } const ve=el('videoPreview'); if(ve)ve.srcObject=null; el('videoPreviewPlaceholder')?.classList.remove('hidden'); }
async function toggleVideoRecord(){
 const btn=el('videoRecBtn'), status=el('videoRecStatus'), playback=el('videoPlayback');
 if(videoRecorder&&videoRecorder.state==='recording'){ videoRecorder.stop(); if(btn)btn.textContent='●'; if(status)status.textContent='PROCESSING'; clearInterval(videoTimerInterval); return; }
 if(!navigator.mediaDevices?.getUserMedia){ showError('Video not supported'); return; }
 try{
  if(!videoStream) await startVideoPreview();
  if(!videoStream) throw new Error('No video stream');
  videoChunks=[]; let mime='video/webm'; if(MediaRecorder.isTypeSupported('video/webm;codecs=vp9'))mime='video/webm;codecs=vp9'; else if(MediaRecorder.isTypeSupported('video/webm;codecs=vp8'))mime='video/webm;codecs=vp8'; else if(MediaRecorder.isTypeSupported('video/mp4'))mime='video/mp4';
  videoRecorder=new MediaRecorder(videoStream,{mimeType:mime});
  videoRecorder.ondataavailable=e=>{ if(e.data.size>0)videoChunks.push(e.data); };
  videoRecorder.onstop=()=>{ const blob=new Blob(videoChunks,{type:videoRecorder.mimeType}); const url=URL.createObjectURL(blob); if(playback){ playback.src=url; playback.classList.remove('hidden'); } const file=new File([blob],`video_${Date.now()}.webm`,{type:blob.type}); setFile(file,file.name); if(status)status.textContent='READY'; log(`Video recorded ${blob.size}`); };
  videoRecorder.start(100); videoStartTime=Date.now();
  if(btn)btn.textContent='■'; if(status){ status.textContent='REC'; status.className='mono text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 border'; }
  videoTimerInterval=setInterval(()=>{ const e=Math.floor((Date.now()-videoStartTime)/1000); const mm=String(Math.floor(e/60)).padStart(2,'0'), ss=String(e%60).padStart(2,'0'); const vt=el('videoRecTimer'); if(vt)vt.textContent=`${mm}:${ss}`; },400);
 }catch(e){ showError('Video error: '+e.message); if(status)status.textContent='BLOCKED'; }
}
async function switchCamera(){ facingMode=facingMode==='user'?'environment':'user'; const s=el('videoRecStatus'); if(s)s.textContent='SWITCHING'; await startVideoPreview(); }
function setRecMode(mode){
 recMode=mode;
 const ap=el('audioRecPanel'), vp=el('videoRecPanel'), ab=el('recModeAudioBtn'), vb=el('recModeVideoBtn');
 if(mode==='audio'){ if(ap)ap.classList.remove('hidden'); if(vp)vp.classList.add('hidden'); if(ab)ab.className='px-3 py-1 rounded-full bg-zinc-900 text-white text-[12px]'; if(vb)vb.className='px-3 py-1 rounded-full text-zinc-600 text-[12px]'; stopVideoPreview(); }
 else { if(ap)ap.classList.add('hidden'); if(vp)vp.classList.remove('hidden'); if(vb)vb.className='px-3 py-1 rounded-full bg-zinc-900 text-white text-[12px]'; if(ab)ab.className='px-3 py-1 rounded-full text-zinc-600 text-[12px]'; startVideoPreview(); }
}

function setupUploadHandlers(){
 const drop=el('dropZone'), fileInput=el('fileInput'), browse=el('browseBtn');
 if(!drop||!fileInput){ log('Upload elements missing'); return; }

 const triggerFilePicker = (e)=>{
  if(e){ e.preventDefault(); e.stopPropagation(); }
  log('Trigger file picker');
  // Reset to allow same file re-select
  fileInput.value='';
  // Use setTimeout to ensure reset processed, and call click in same tick as user gesture
  try{
   fileInput.click();
  }catch(err){ log('fileInput.click failed: '+err.message); showError('Browse not supported, try drag & drop'); }
 };

 // Browse button - most reliable
 if(browse){
  browse.addEventListener('click', triggerFilePicker);
  // also touch
  browse.addEventListener('touchend', triggerFilePicker, {passive:false});
 }

 // Drop zone click - but ignore if clicking browseBtn (already handled) or fileInfo etc
 drop.addEventListener('click', (e)=>{
  if(e.target.closest('#browseBtn')) return;
  if(e.target.closest('#fileInfo')) return;
  triggerFilePicker(e);
 });

 // Drag and drop
 ['dragenter','dragover'].forEach(ev=>{
  drop.addEventListener(ev, e=>{ e.preventDefault(); e.stopPropagation(); drop.classList.add('border-[#e85d26]/50','bg-[#fff7ed]'); });
 });
 ['dragleave','drop'].forEach(ev=>{
  drop.addEventListener(ev, e=>{ e.preventDefault(); e.stopPropagation(); drop.classList.remove('border-[#e85d26]/50','bg-[#fff7ed]'); });
 });
 drop.addEventListener('drop', e=>{
  e.preventDefault(); e.stopPropagation();
  const f=e.dataTransfer.files[0];
  if(f){
   log(`Dropped file: ${f.name} ${f.size}`);
   if(f.size>50*1024*1024){ showError('File too large, max 50MB'); return; }
   setFile(f,f.name);
  }
 });

 fileInput.addEventListener('change', ()=>{
  const f=fileInput.files[0];
  if(f){
   log(`Selected via input: ${f.name} ${f.size} type=${f.type}`);
   if(f.size>50*1024*1024){ showError('File too large, max 50MB'); fileInput.value=''; return; }
   setFile(f,f.name);
  } else {
   log('fileInput change but no file');
  }
 });

 // Also support label click fallback: if user clicks anywhere in dropZone, fileInput will work

 el('clearFile').onclick=clearFile;
 el('generateBtn').onclick=uploadAndGenerate;
 el('recBtn').onclick=toggleRecord;
 el('videoRecBtn').onclick=toggleVideoRecord;
 el('switchCameraBtn').onclick=switchCamera;
 el('recModeAudioBtn').onclick=()=>setRecMode('audio');
 el('recModeVideoBtn').onclick=()=>setRecMode('video');
 el('refreshJobs').onclick=loadJobs;

 // Delete modal handlers
 const dm=el('deleteModal'), dmo=el('deleteModalOverlay'), dmc=el('deleteModalCancel'), dmcf=el('deleteModalConfirm');
 if(dmo) dmo.onclick=closeDeleteModal;
 if(dmc) dmc.onclick=closeDeleteModal;
 if(dmcf) dmcf.onclick=confirmDelete;
 document.addEventListener('keydown', (e)=>{ if(e.key==='Escape'){ if(dm&&!dm.classList.contains('hidden')) closeDeleteModal(); } });

 // Old delete buttons replaced by modal
 el('clearAllBtn').onclick=()=>{ openDeleteModal(null,'clearAll'); };
 el('deleteCurrentBtn').onclick=()=>{ if(currentJobId) openDeleteModal(currentJobId,'single'); else showError('No current song'); };
 el('newSongBtn').onclick=()=>{
  clearFile(); el('progressCard')?.classList.add('hidden'); el('resultView')?.classList.add('hidden'); el('createView')?.classList.remove('hidden'); hideError();
  if(audioCtx){ try{audioCtx.close();}catch{} audioCtx=null; } isMixerReady=false; window.scrollTo({top:0,behavior:'smooth'});
 };
 el('shareBtn').onclick=()=>{
  if(!currentJobId)return; const url=`${location.origin}/api/jobs/${currentJobId}/files/final.mp3`;
  if(navigator.share) navigator.share({title:'My Just Sing song',url}).catch(()=>{});
  else navigator.clipboard.writeText(url).then(()=>alert('Link copied: '+url));
 };
 el('renderCustomMixBtn').onclick=renderCustomMixOnServer;
 log('Upload handlers v42 - fileInput offscreen, browse fixed, delete modal icon');
}

document.addEventListener('DOMContentLoaded',()=>{
 log('Just Sing v42 FIXED browse + delete modal icon + v1.7 chorus');
 initLiveBars(); loadJobs(); setupUploadHandlers(); renderWaveforms();
 fetch('/api/jobs?limit=1').then(r=>r.json()).then(j=>{ log('Backend ready: '+(j.jobs?j.jobs.length:0)+' songs'); }).catch(e=>{ showError('Backend not reachable: '+e.message); });
});
