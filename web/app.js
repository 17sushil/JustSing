/* SingSmith Frontend v0.2 — fixed for sandbox preview */
const STYLES = [
  { id: 'warm-acoustic', name: 'Warm Acoustic', desc: 'Guitar + soft drums', emoji: '🎸' },
  { id: 'lofi-chill', name: 'LoFi Chill', desc: 'Mellow, vinyl crackle', emoji: '🌙' },
  { id: 'piano-ballad', name: 'Piano Ballad', desc: 'Intimate piano', emoji: '🎹' },
  { id: 'indie-pop', name: 'Indie Pop', desc: 'Bright, upbeat', emoji: '✨' },
  { id: 'cinematic', name: 'Cinematic', desc: 'Epic, spacious', emoji: '🎬' },
];

let selectedStyle = 'warm-acoustic';
let selectedFile = null;
let currentJobId = null;
let pollTimer = null;
let recChunks = [];
let mediaRecorder = null;
let recStartTime = null;
let recTimerInterval = null;

const el = (id) => document.getElementById(id);
const log = (msg) => {
  console.log(msg);
  const d = el('debugLog');
  if(d){
    d.textContent = `[${new Date().toLocaleTimeString()}] ${msg}\n` + d.textContent.slice(0,3000);
  }
};
const showError = (msg) => {
  const box = el('errorBox');
  box.textContent = msg;
  box.classList.remove('hidden');
  log('ERROR: ' + msg);
};
const hideError = () => {
  el('errorBox').classList.add('hidden');
};

function initStylePicker() {
  const container = el('stylePicker');
  container.innerHTML = '';
  STYLES.forEach(s => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `text-left rounded-2xl border p-3 bg-white hover:border-purple-300 transition ${s.id===selectedStyle?'border-purple-500 ring-2 ring-purple-100': 'border-zinc-200'}`;
    btn.innerHTML = `<div class="flex items-center gap-2"><span class="text-lg">${s.emoji}</span><span class="font-semibold text-sm">${s.name}</span></div><div class="text-[11px] text-zinc-500 mt-1">${s.desc}</div>`;
    btn.onclick = () => { selectedStyle = s.id; initStylePicker(); if(selectedFile) el('fileMeta').textContent = `${(selectedFile.size/1024/1024).toFixed(2)} MB • ${selectedStyle}`; };
    container.appendChild(btn);
  });
}

function initLiveBars() {
  const c = el('liveBars');
  if(!c) return;
  c.innerHTML = '';
  for(let i=0;i<16;i++){
    const b = document.createElement('div');
    b.className = 'w-[3px] bg-zinc-200 rounded-full';
    b.style.height = '6px';
    c.appendChild(b);
  }
}

function setFile(file, nameHint) {
  selectedFile = file;
  el('fileInfo').classList.remove('hidden');
  el('fileName').textContent = nameHint || file.name || 'recording.webm';
  const sizeMB = (file.size/1024/1024).toFixed(2);
  el('fileMeta').textContent = `${sizeMB} MB • ${selectedStyle} • ${file.type||'audio'}`;
  el('generateBtn').disabled = false;
  el('generateBtn').className = 'w-full h-[56px] rounded-full bg-zinc-900 text-white font-semibold tracking-wide hover:bg-black transition flex items-center justify-center gap-2 shadow-lg';
  hideError();
  log(`File selected: ${nameHint||file.name} ${sizeMB}MB ${file.type}`);
}

function clearFile() {
  selectedFile = null;
  el('fileInfo').classList.add('hidden');
  const inp = el('fileInput');
  if(inp) inp.value = '';
  el('generateBtn').disabled = true;
  el('generateBtn').className = 'w-full h-[56px] rounded-full bg-zinc-300 text-zinc-500 font-semibold tracking-wide cursor-not-allowed transition flex items-center justify-center gap-2';
  log('File cleared');
}

async function uploadAndGenerate() {
  if(!selectedFile){
    showError('No file selected. Please drop a file or record first.');
    return;
  }
  hideError();
  const fd = new FormData();
  fd.append('file', selectedFile, selectedFile.name || 'upload.webm');
  fd.append('style', selectedStyle);

  el('progressCard').classList.remove('hidden');
  el('resultCard').classList.add('hidden');
  el('progressBar').style.width = '5%';
  el('progressPct').textContent = '5%';
  el('progressMsg').textContent = 'Uploading...';
  el('analysisBox').classList.add('hidden');

  log(`Uploading ${selectedFile.name} as ${selectedStyle}...`);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: fd });
    const text = await res.text();
    log(`Upload response ${res.status}: ${text.slice(0,500)}`);
    if(!res.ok){
      throw new Error(`Upload failed ${res.status}: ${text.slice(0,300)}`);
    }
    const data = JSON.parse(text);
    currentJobId = data.job_id;
    log(`Job created: ${currentJobId}`);
    pollJob(currentJobId);
  } catch(e) {
    showError('Upload failed: ' + e.message + ' — Try /test-upload fallback. Check debug console.');
    el('progressMsg').textContent = 'Upload failed: ' + e.message;
    el('progressBar').style.width = '100%';
    el('progressBar').style.background = '#ef4444';
    log('Upload exception: ' + e.stack);
  }
}

function pollJob(jobId) {
  if(pollTimer) clearInterval(pollTimer);
  log(`Start polling ${jobId}`);
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if(!res.ok) throw new Error('job not found ' + res.status);
      const job = await res.json();
      const pct = job.progress || 0;
      el('progressBar').style.width = `${pct}%`;
      el('progressPct').textContent = `${pct}%`;
      el('progressMsg').textContent = job.message || job.status;

      if(job.analysis){
        el('analysisBox').classList.remove('hidden');
        el('aKey').textContent = job.analysis.key || '—';
        el('aBpm').textContent = `${job.analysis.bpm || '—'} BPM`;
        el('aRange').textContent = `${Math.round(job.analysis.f0_min_hz||0)}–${Math.round(job.analysis.f0_max_hz||0)} Hz`;
        el('aLang').textContent = job.analysis.language || 'unknown';
      }

      if(job.status === 'completed'){
        clearInterval(pollTimer);
        log(`Job ${jobId} completed`);
        showResult(job);
        loadJobs();
      } else if(job.status === 'failed'){
        clearInterval(pollTimer);
        showError('Generation failed: ' + (job.error || job.message));
        el('progressMsg').textContent = 'Failed: ' + (job.error || job.message);
        el('progressBar').style.background = '#ef4444';
        log(`Job failed: ${JSON.stringify(job).slice(0,1000)}`);
      }
    } catch(e){
      log('Poll error: ' + e.message);
    }
  }, 1200);
}

function showResult(job) {
  el('resultCard').classList.remove('hidden');
  const files = job.files || {};
  el('resultMeta').textContent = `${job.analysis?.key || ''} • ${job.analysis?.bpm || ''} BPM • ${job.analysis?.duration_sec || ''}s • ${job.style}`;

  if(files.mp3){
    el('finalAudio').src = files.mp3;
    el('dlMp3').href = files.mp3;
  }
  if(files.wav){
    el('dlWav').href = files.wav;
  }
  if(files.vocal){
    el('vocalAudio').src = files.vocal;
  }
  if(files.accompaniment){
    el('accAudio').src = files.accompaniment;
  }
  if(job.analysis?.lyrics_preview){
    el('lyricsBox').classList.remove('hidden');
    el('lyricsText').textContent = job.analysis.lyrics_preview;
  }
  el('resultCard').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadJobs(){
  try{
    const res = await fetch('/api/jobs?limit=10');
    const data = await res.json();
    const list = el('jobsList');
    if(!data.jobs || data.jobs.length===0){
      list.textContent = 'No songs yet — be the first!';
      return;
    }
    list.innerHTML = '';
    data.jobs.forEach(j=>{
      const div = document.createElement('div');
      div.className = 'flex items-center justify-between p-2 rounded-xl hover:bg-zinc-50 cursor-pointer border border-transparent hover:border-zinc-200';
      const statusDot = j.status==='completed' ? '🟢' : j.status==='failed' ? '🔴' : '🟡';
      div.innerHTML = `<div class="truncate"><span>${statusDot}</span> <span class="font-medium">${j.job_id.slice(0,8)}</span> <span class="text-zinc-400">${j.style||''} ${j.analysis? j.analysis.key:''}</span></div><div class="text-[10px]">${j.progress||0}%</div>`;
      div.onclick = ()=>{
        currentJobId = j.job_id;
        el('progressCard').classList.remove('hidden');
        if(j.status==='completed') showResult(j);
        else pollJob(j.job_id);
      };
      list.appendChild(div);
    });
  }catch(e){
    el('jobsList').textContent = 'Failed to load: ' + e.message;
    log('loadJobs failed: ' + e.message);
  }
}

async function toggleRecord(){
  const btn = el('recBtn');
  const status = el('recStatus');
  const hint = el('recHint');
  if(mediaRecorder && mediaRecorder.state === 'recording'){
    mediaRecorder.stop();
    btn.textContent = '●';
    btn.className = 'w-14 h-14 rounded-full bg-gradient-to-br from-red-500 to-pink-500 text-white text-xl flex items-center justify-center shadow-lg hover:scale-105 transition';
    status.textContent = 'processing';
    status.className = 'text-[10px] mono px-2 py-1 rounded-full bg-zinc-100';
    clearInterval(recTimerInterval);
    log('Recording stopped');
    return;
  }

  // Check support
  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
    showError('Recording not supported in this browser/iframe. Please use upload instead, or open preview in new tab.');
    log('mediaDevices not available');
    return;
  }

  try{
    log('Requesting microphone...');
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation:true, noiseSuppression:true } });
    log('Microphone granted');
    recChunks = [];
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
    log('Using mimeType: ' + mimeType);
    mediaRecorder = new MediaRecorder(stream, { mimeType });
    mediaRecorder.ondataavailable = e=>{ if(e.data.size>0) recChunks.push(e.data); log(`Chunk ${e.data.size} bytes`); };
    mediaRecorder.onerror = e=>{ showError('Recorder error: ' + e.error); log('Recorder error: ' + e.error); };
    mediaRecorder.onstop = ()=>{
      const blob = new Blob(recChunks, { type: mediaRecorder.mimeType });
      const url = URL.createObjectURL(blob);
      const preview = el('recPreview');
      preview.src = url;
      preview.classList.remove('hidden');
      const file = new File([blob], `recording_${Date.now()}.webm`, { type: blob.type });
      setFile(file, file.name);
      status.textContent = 'ready';
      hint.textContent = 'Recording ready — hit Generate!';
      stream.getTracks().forEach(t=>t.stop());
      log(`Recording blob ${blob.size} bytes ready`);
    };
    mediaRecorder.start(100);
    recStartTime = Date.now();
    btn.textContent = '■';
    btn.className = 'w-14 h-14 rounded-full bg-zinc-900 text-white text-xl flex items-center justify-center shadow-lg animate-pulse';
    status.textContent = 'recording';
    status.className = 'text-[10px] mono px-2 py-1 rounded-full bg-red-100 text-red-600';
    hint.textContent = 'Recording... sing now!';

    recTimerInterval = setInterval(()=>{
      const elapsed = Math.floor((Date.now()-recStartTime)/1000);
      const mm = String(Math.floor(elapsed/60)).padStart(2,'0');
      const ss = String(elapsed%60).padStart(2,'0');
      el('recTimer').textContent = `${mm}:${ss}`;
    }, 500);

    // Visualizer
    try{
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const bars = el('liveBars').children;
      const loop = ()=>{
        if(!mediaRecorder || mediaRecorder.state !== 'recording'){ try{audioCtx.close();}catch{} return; }
        analyser.getByteFrequencyData(dataArray);
        for(let i=0;i<bars.length;i++){
          const v = dataArray[i*2] / 255;
          bars[i].style.height = `${6 + v*36}px`;
          bars[i].className = 'w-[3px] bg-purple-500 rounded-full transition-all duration-75';
        }
        requestAnimationFrame(loop);
      };
      loop();
    }catch(e){
      log('Visualizer failed: ' + e.message);
    }
  }catch(e){
    const msg = e.name === 'NotAllowedError' ? 'Microphone permission denied. Please allow mic and try again. In Arena preview iframe, you may need to open in new tab.' : e.message;
    showError('Microphone error: ' + msg);
    log('getUserMedia failed: ' + e.name + ' ' + e.message);
    el('recStatus').textContent = 'blocked';
    el('recHint').textContent = 'Mic blocked — use upload or open preview in new tab.';
  }
}

document.addEventListener('DOMContentLoaded', ()=>{
  log(`Frontend loaded. Origin: ${location.origin} Host: ${location.host} Protocol: ${location.protocol}`);
  el('originInfo').textContent = `Origin: ${location.origin} | If recording fails, open this URL in new tab and allow mic. Upload always works.`;

  initStylePicker();
  initLiveBars();
  loadJobs();

  const drop = el('dropZone');
  const fileInput = el('fileInput');

  // Make sure click on dropZone opens file picker even if event bubbles
  const openPicker = (e) => {
    e.preventDefault();
    e.stopPropagation();
    fileInput.click();
  };
  drop.addEventListener('click', openPicker);

  fileInput.addEventListener('change', ()=>{
    log(`File input change: ${fileInput.files.length} files`);
    if(fileInput.files && fileInput.files[0]){
      setFile(fileInput.files[0], fileInput.files[0].name);
    }
  });

  // Drag & drop
  ['dragenter','dragover'].forEach(ev=>{
    drop.addEventListener(ev, e=>{ e.preventDefault(); e.stopPropagation(); drop.classList.add('border-purple-500','bg-purple-50'); });
  });
  ['dragleave','drop'].forEach(ev=>{
    drop.addEventListener(ev, e=>{ e.preventDefault(); e.stopPropagation(); drop.classList.remove('border-purple-500','bg-purple-50'); });
  });
  drop.addEventListener('drop', e=>{
    e.preventDefault();
    e.stopPropagation();
    const f = e.dataTransfer.files[0];
    log(`Drop: ${f?f.name:'no file'}`);
    if(f){
      // Validate type
      if(!f.type.startsWith('audio/') && !f.type.startsWith('video/') && !/\.(mp3|wav|m4a|mp4|webm|ogg|flac|mov|aac|opus)$/i.test(f.name)){
        showError(`Unsupported file type: ${f.type||f.name}. Try MP3, WAV, M4A, MP4, WebM.`);
        return;
      }
      setFile(f, f.name);
    }
  });

  el('clearFile').onclick = clearFile;
  el('generateBtn').onclick = uploadAndGenerate;
  el('recBtn').onclick = toggleRecord;
  el('refreshJobs').onclick = loadJobs;
  el('newSongBtn').onclick = ()=>{
    clearFile();
    el('progressCard').classList.add('hidden');
    el('resultCard').classList.add('hidden');
    hideError();
    window.scrollTo({ top:0, behavior:'smooth' });
  };
  el('shareBtn').onclick = ()=>{
    if(!currentJobId) return;
    const url = `${location.origin}/api/jobs/${currentJobId}/files/final.mp3`;
    if(navigator.share){
      navigator.share({ title: 'My SingSmith song', url }).catch(()=>{});
    } else {
      navigator.clipboard.writeText(url).then(()=>alert('Link copied: ' + url)).catch(()=>alert(url));
    }
  };

  // Test API connectivity
  fetch('/api/health').then(r=>r.json()).then(j=>log('API health: ' + JSON.stringify(j))).catch(e=>{ showError('API not reachable: ' + e.message); log('Health check failed: ' + e.message); });
});
