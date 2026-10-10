/* SingSmith Frontend v1.6 — REAL PIANO + VOLUME MIXER */
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

// Volume mixer state
let audioCtx = null;
let vocalBuffer = null;
let accBuffer = null;
let vocalGainNode = null;
let accGainNode = null;
let masterGainNode = null;
let isMixerReady = false;
let currentSources = [];

const el = (id) => document.getElementById(id);
const log = (msg) => {
  console.log(msg);
  const d = el('debugLog');
  if(d){
    d.textContent = `[${new Date().toLocaleTimeString()}] ${msg}\n` + d.textContent.slice(0,5000);
  }
};
const showError = (msg) => {
  const box = el('errorBox');
  if(!box) return;
  box.textContent = msg;
  box.classList.remove('hidden');
  log('ERROR: ' + msg);
};
const hideError = () => {
  const b = el('errorBox');
  if(b) b.classList.add('hidden');
};

function initStylePicker() {
  const container = el('stylePicker');
  if(!container) return;
  container.innerHTML = '';
  STYLES.forEach(s => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `text-left rounded-2xl border p-3 bg-white hover:border-purple-300 transition ${s.id===selectedStyle?'border-purple-500 ring-2 ring-purple-100': 'border-zinc-200'}`;
    btn.innerHTML = `<div class="flex items-center gap-2"><span class="text-lg">${s.emoji}</span><span class="font-semibold text-sm">${s.name}</span></div><div class="text-[11px] text-zinc-500 mt-1">${s.desc}</div>`;
    btn.onclick = () => { 
      selectedStyle = s.id; 
      initStylePicker(); 
      if(selectedFile && el('fileMeta')) el('fileMeta').textContent = `${(selectedFile.size/1024/1024).toFixed(2)} MB • ${selectedStyle}`;
      log('Style selected: ' + selectedStyle);
    };
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
  if(!file){
    log('setFile called with null');
    return;
  }
  selectedFile = file;
  log(`File set: name=${nameHint||file.name} size=${file.size} type=${file.type}`);
  const fileInfo = el('fileInfo');
  if(fileInfo) fileInfo.classList.remove('hidden');
  const fileNameEl = el('fileName');
  if(fileNameEl) fileNameEl.textContent = nameHint || file.name || 'recording.webm';
  const sizeMB = (file.size/1024/1024).toFixed(2);
  const fileMetaEl = el('fileMeta');
  if(fileMetaEl) fileMetaEl.textContent = `${sizeMB} MB • ${selectedStyle} • ${file.type||'audio'}`;
  const genBtn = el('generateBtn');
  if(genBtn){
    genBtn.disabled = false;
    genBtn.className = 'w-full h-[56px] rounded-full bg-zinc-900 text-white font-semibold tracking-wide hover:bg-black transition flex items-center justify-center gap-2 shadow-lg cursor-pointer';
    genBtn.innerHTML = '<span>Generate my song</span><span>→</span>';
  }
  hideError();
}

function clearFile() {
  selectedFile = null;
  const fileInfo = el('fileInfo');
  if(fileInfo) fileInfo.classList.add('hidden');
  const inp = el('fileInput');
  if(inp) inp.value = '';
  const inp2 = el('fileInputFallback');
  if(inp2) inp2.value = '';
  const genBtn = el('generateBtn');
  if(genBtn){
    genBtn.disabled = true;
    genBtn.className = 'w-full h-[56px] rounded-full bg-zinc-300 text-zinc-500 font-semibold tracking-wide cursor-not-allowed transition flex items-center justify-center gap-2';
    genBtn.innerHTML = '<span>Select a file first</span>';
  }
  log('File cleared');
}

async function uploadAndGenerate() {
  log('uploadAndGenerate clicked, selectedFile=' + (selectedFile?selectedFile.name:'null'));
  if(!selectedFile){
    showError('No file selected. Please drop a file, click Browse, or record first.');
    return;
  }
  hideError();
  const fd = new FormData();
  const fileName = selectedFile.name || `upload_${Date.now()}.webm`;
  fd.append('file', selectedFile, fileName);
  fd.append('style', selectedStyle);

  const progressCard = el('progressCard');
  if(progressCard) progressCard.classList.remove('hidden');
  const resultCard = el('resultCard');
  if(resultCard) resultCard.classList.add('hidden');
  const progressBar = el('progressBar');
  if(progressBar){
    progressBar.style.width = '5%';
    progressBar.style.background = '';
  }
  const progressPct = el('progressPct');
  if(progressPct) progressPct.textContent = '5%';
  const progressMsg = el('progressMsg');
  if(progressMsg) progressMsg.textContent = 'Uploading...';
  const analysisBox = el('analysisBox');
  if(analysisBox) analysisBox.classList.add('hidden');

  log(`Uploading ${fileName} (${(selectedFile.size/1024).toFixed(1)}KB) as ${selectedStyle} to /api/upload`);

  try {
    const res = await fetch('/api/upload', { method: 'POST', body: fd });
    const text = await res.text();
    log(`Upload response ${res.status}: ${text.slice(0,800)}`);
    if(!res.ok){
      throw new Error(`Upload failed ${res.status}: ${text.slice(0,500)}`);
    }
    let data;
    try{
      data = JSON.parse(text);
    }catch(e){
      throw new Error('Invalid JSON response: ' + text.slice(0,300));
    }
    currentJobId = data.job_id;
    if(!currentJobId){
      throw new Error('No job_id in response: ' + text.slice(0,300));
    }
    log(`Job created: ${currentJobId}`);
    if(progressMsg) progressMsg.textContent = 'Queued... job ' + currentJobId.slice(0,8);
    pollJob(currentJobId);
  } catch(e) {
    showError('Upload failed: ' + e.message + ' — Try /test-upload fallback. Check debug console below.');
    if(progressMsg) progressMsg.textContent = 'Upload failed: ' + e.message;
    if(progressBar){
      progressBar.style.width = '100%';
      progressBar.style.background = '#ef4444';
    }
    log('Upload exception: ' + e.message + '\n' + (e.stack||''));
  }
}

function pollJob(jobId) {
  if(pollTimer) clearInterval(pollTimer);
  log(`Start polling ${jobId}`);
  const poll = async () => {
    try {
      const res = await fetch(`/api/jobs/${jobId}`);
      if(!res.ok) throw new Error('job not found ' + res.status);
      const job = await res.json();
      const pct = job.progress || 0;
      const progressBar = el('progressBar');
      if(progressBar) progressBar.style.width = `${pct}%`;
      const progressPct = el('progressPct');
      if(progressPct) progressPct.textContent = `${pct}%`;
      const progressMsg = el('progressMsg');
      if(progressMsg) progressMsg.textContent = job.message || job.status;

      if(job.analysis){
        const analysisBox = el('analysisBox');
        if(analysisBox) analysisBox.classList.remove('hidden');
        const aKey = el('aKey');
        if(aKey) aKey.textContent = job.analysis.key || '—';
        const aBpm = el('aBpm');
        if(aBpm) aBpm.textContent = `${job.analysis.bpm || '—'} BPM`;
        const aRange = el('aRange');
        if(aRange) aRange.textContent = `${Math.round(job.analysis.f0_min_hz||0)}–${Math.round(job.analysis.f0_max_hz||0)} Hz`;
        const aLang = el('aLang');
        if(aLang) aLang.textContent = job.analysis.language || 'unknown';
      }

      if(job.status === 'completed'){
        clearInterval(pollTimer);
        pollTimer = null;
        log(`Job ${jobId} completed`);
        showResult(job);
        loadJobs();
      } else if(job.status === 'failed'){
        clearInterval(pollTimer);
        pollTimer = null;
        const errMsg = job.error || job.message || 'unknown error';
        showError('Generation failed: ' + errMsg);
        if(progressMsg) progressMsg.textContent = 'Failed: ' + errMsg;
        if(progressBar) progressBar.style.background = '#ef4444';
        log(`Job failed: ${JSON.stringify(job).slice(0,1500)}`);
      }
    } catch(e){
      log('Poll error: ' + e.message);
    }
  };
  poll();
  pollTimer = setInterval(poll, 1200);
}

// VOLUME MIXER v1.6
async function initVolumeMixer(vocalUrl, accUrl) {
  log(`Init volume mixer: vocal=${vocalUrl.slice(0,60)}... acc=${accUrl.slice(0,60)}...`);
  const status = el('customMixStatus');
  if(status) status.textContent = 'Loading stems for mixer...';
  
  try {
    if(!audioCtx){
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      log('AudioContext created: ' + audioCtx.sampleRate + 'Hz');
    }
    
    // Fetch and decode both
    const [vocalResp, accResp] = await Promise.all([
      fetch(vocalUrl),
      fetch(accUrl)
    ]);
    
    if(!vocalResp.ok || !accResp.ok){
      throw new Error(`Failed to fetch stems: vocal ${vocalResp.status}, acc ${accResp.status}`);
    }
    
    const [vocalArrayBuf, accArrayBuf] = await Promise.all([
      vocalResp.arrayBuffer(),
      accResp.arrayBuffer()
    ]);
    
    log(`Fetched stems: vocal ${vocalArrayBuf.byteLength} bytes, acc ${accArrayBuf.byteLength} bytes, decoding...`);
    
    const [vocalBuf, accBuf] = await Promise.all([
      audioCtx.decodeAudioData(vocalArrayBuf.slice(0)),
      audioCtx.decodeAudioData(accArrayBuf.slice(0))
    ]);
    
    vocalBuffer = vocalBuf;
    accBuffer = accBuf;
    
    log(`Decoded: vocal ${vocalBuf.duration.toFixed(2)}s ${vocalBuf.numberOfChannels}ch, acc ${accBuf.duration.toFixed(2)}s ${accBuf.numberOfChannels}ch`);
    
    // Create gain nodes
    vocalGainNode = audioCtx.createGain();
    accGainNode = audioCtx.createGain();
    masterGainNode = audioCtx.createGain();
    
    vocalGainNode.gain.value = 1.0;
    accGainNode.gain.value = 0.35;
    masterGainNode.gain.value = 1.0;
    
    vocalGainNode.connect(masterGainNode);
    accGainNode.connect(masterGainNode);
    masterGainNode.connect(audioCtx.destination);
    
    isMixerReady = true;
    log('Volume mixer ready! Adjust sliders for real-time mixing');
    if(status) status.textContent = 'Mixer ready — adjust sliders for real-time preview';
    
    // Setup slider listeners
    setupMixerSliders();
    
    // Create initial mixed preview file via offline rendering
    await renderMixedPreview();
    
  } catch(e) {
    log('Mixer init failed: ' + e.message + '\n' + (e.stack||'').slice(0,1000));
    if(status) status.textContent = 'Mixer load failed: ' + e.message + ' — you can still download stems';
    isMixerReady = false;
  }
}

function setupMixerSliders() {
  const vocalSlider = el('vocalGainSlider');
  const accSlider = el('accGainSlider');
  const masterSlider = el('masterGainSlider');
  const vocalLabel = el('vocalGainLabel');
  const accLabel = el('accGainLabel');
  const masterLabel = el('masterGainLabel');
  
  if(!vocalSlider || !accSlider || !masterSlider) {
    log('Mixer sliders not found');
    return;
  }
  
  const updateVocal = () => {
    const val = parseInt(vocalSlider.value);
    const gain = val / 100;
    if(vocalLabel) vocalLabel.textContent = val + '%';
    if(vocalGainNode) vocalGainNode.gain.value = gain;
    log(`Vocal gain: ${val}% (${gain.toFixed(2)})`);
    // Debounce preview render
    debounceRenderPreview();
  };
  
  const updateAcc = () => {
    const val = parseInt(accSlider.value);
    const gain = val / 100;
    if(accLabel) accLabel.textContent = val + '%';
    if(accGainNode) accGainNode.gain.value = gain;
    log(`Track gain: ${val}% (${gain.toFixed(2)})`);
    debounceRenderPreview();
  };
  
  const updateMaster = () => {
    const val = parseInt(masterSlider.value);
    const gain = val / 100;
    if(masterLabel) masterLabel.textContent = val + '%';
    if(masterGainNode) masterGainNode.gain.value = gain;
    log(`Master gain: ${val}% (${gain.toFixed(2)})`);
    debounceRenderPreview();
  };
  
  vocalSlider.addEventListener('input', updateVocal);
  accSlider.addEventListener('input', updateAcc);
  masterSlider.addEventListener('input', updateMaster);
  
  const resetBtn = el('resetMixerBtn');
  if(resetBtn){
    resetBtn.onclick = () => {
      vocalSlider.value = 100;
      accSlider.value = 35;
      masterSlider.value = 100;
      updateVocal();
      updateAcc();
      updateMaster();
      log('Mixer reset to defaults: vocal 100%, track 35%, master 100%');
    };
  }
  
  log('Mixer sliders listeners attached');
}

let renderDebounceTimer = null;
function debounceRenderPreview() {
  if(renderDebounceTimer) clearTimeout(renderDebounceTimer);
  renderDebounceTimer = setTimeout(() => {
    renderMixedPreview();
  }, 500);
}

async function renderMixedPreview() {
  if(!isMixerReady || !vocalBuffer || !accBuffer || !audioCtx) {
    log('renderMixedPreview: not ready');
    return;
  }
  
  const vocalSlider = el('vocalGainSlider');
  const accSlider = el('accGainSlider');
  const masterSlider = el('masterGainSlider');
  
  const vocalGain = vocalSlider ? parseInt(vocalSlider.value)/100 : 1.0;
  const accGain = accSlider ? parseInt(accSlider.value)/100 : 0.35;
  const masterGain = masterSlider ? parseInt(masterSlider.value)/100 : 1.0;
  
  log(`Rendering mixed preview: vocal ${vocalGain.toFixed(2)}, acc ${accGain.toFixed(2)}, master ${masterGain.toFixed(2)}`);
  
  try {
    // Use OfflineAudioContext to render mixed buffer
    const duration = Math.max(vocalBuffer.duration, accBuffer.duration);
    const sampleRate = audioCtx.sampleRate;
    const offlineCtx = new OfflineAudioContext(2, Math.ceil(duration * sampleRate), sampleRate);
    
    // Create sources
    const vocalSrc = offlineCtx.createBufferSource();
    vocalSrc.buffer = vocalBuffer;
    const vocalGainNodeOffline = offlineCtx.createGain();
    vocalGainNodeOffline.gain.value = vocalGain;
    vocalSrc.connect(vocalGainNodeOffline);
    
    const accSrc = offlineCtx.createBufferSource();
    accSrc.buffer = accBuffer;
    const accGainNodeOffline = offlineCtx.createGain();
    accGainNodeOffline.gain.value = accGain;
    accSrc.connect(accGainNodeOffline);
    
    const masterGainOffline = offlineCtx.createGain();
    masterGainOffline.gain.value = masterGain;
    
    vocalGainNodeOffline.connect(masterGainOffline);
    accGainNodeOffline.connect(masterGainOffline);
    masterGainOffline.connect(offlineCtx.destination);
    
    vocalSrc.start(0);
    accSrc.start(0);
    
    const renderedBuffer = await offlineCtx.startRendering();
    log(`Offline rendered: ${renderedBuffer.duration.toFixed(2)}s`);
    
    // Convert to WAV blob for preview
    const wavBlob = bufferToWavBlob(renderedBuffer);
    const url = URL.createObjectURL(wavBlob);
    const previewAudio = el('mixedPreviewAudio');
    if(previewAudio){
      previewAudio.src = url;
      // Don't auto-play, let user click play
    }
    
    // Store for download (optional client-side download)
    window._lastMixedWavBlob = wavBlob;
    window._lastMixedGains = { vocalGain, accGain, masterGain };
    
  } catch(e) {
    log('renderMixedPreview failed: ' + e.message);
  }
}

function bufferToWavBlob(buffer) {
  const numChannels = buffer.numberOfChannels;
  const sampleRate = buffer.sampleRate;
  const length = buffer.length;
  const interleaved = new Float32Array(length * numChannels);
  
  for(let ch=0; ch<numChannels; ch++){
    const channelData = buffer.getChannelData(ch);
    for(let i=0; i<length; i++){
      interleaved[i*numChannels + ch] = channelData[i];
    }
  }
  
  // Convert float to 16-bit PCM
  const wavLength = 44 + interleaved.length * 2;
  const wavBuffer = new ArrayBuffer(wavLength);
  const view = new DataView(wavBuffer);
  
  // WAV header
  const writeString = (offset, str) => {
    for(let i=0;i<str.length;i++) view.setUint8(offset+i, str.charCodeAt(i));
  };
  
  writeString(0, 'RIFF');
  view.setUint32(4, wavLength-8, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * 2, true);
  view.setUint16(32, numChannels * 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, interleaved.length * 2, true);
  
  let offset = 44;
  for(let i=0;i<interleaved.length;i++){
    const s = Math.max(-1, Math.min(1, interleaved[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    offset += 2;
  }
  
  return new Blob([view], { type: 'audio/wav' });
}

async function renderCustomMixOnServer() {
  if(!currentJobId){
    showError('No job ID for custom mix');
    return;
  }
  
  const vocalSlider = el('vocalGainSlider');
  const accSlider = el('accGainSlider');
  const masterSlider = el('masterGainSlider');
  const status = el('customMixStatus');
  const resultDiv = el('customMixResult');
  
  const vocalGain = vocalSlider ? parseInt(vocalSlider.value)/100 : 1.0;
  const accGain = accSlider ? parseInt(accSlider.value)/100 : 0.35;
  const masterGain = masterSlider ? parseInt(masterSlider.value)/100 : 1.0;
  
  log(`Requesting server custom mix: vocal ${vocalGain}, acc ${accGain}, master ${masterGain} for job ${currentJobId}`);
  if(status) status.textContent = `Rendering custom mix on server: vocal ${Math.round(vocalGain*100)}% acc ${Math.round(accGain*100)}% master ${Math.round(masterGain*100)}%...`;
  
  try {
    const fd = new FormData();
    fd.append('vocal_gain', vocalGain.toString());
    fd.append('acc_gain', accGain.toString());
    fd.append('master_gain', masterGain.toString());
    
    const res = await fetch(`/api/jobs/${currentJobId}/mix-custom`, {
      method: 'POST',
      body: fd
    });
    
    const text = await res.text();
    log(`Custom mix response ${res.status}: ${text.slice(0,800)}`);
    
    if(!res.ok){
      throw new Error(`Server mix failed ${res.status}: ${text.slice(0,500)}`);
    }
    
    const data = JSON.parse(text);
    log(`Custom mix success: ${JSON.stringify(data).slice(0,500)}`);
    
    if(resultDiv) resultDiv.classList.remove('hidden');
    const customAudio = el('customMixAudio');
    if(customAudio && data.files){
      customAudio.src = data.files.mp3 || data.files.wav;
    }
    const dlMp3 = el('dlCustomMp3');
    if(dlMp3 && data.files){
      dlMp3.href = data.files.mp3 || data.files.wav;
      dlMp3.download = `custom_mix_v${Math.round(vocalGain*100)}_a${Math.round(accGain*100)}_m${Math.round(masterGain*100)}.mp3`;
    }
    const dlWav = el('dlCustomWav');
    if(dlWav && data.files){
      dlWav.href = data.files.wav;
      dlWav.download = `custom_mix_v${Math.round(vocalGain*100)}_a${Math.round(accGain*100)}_m${Math.round(masterGain*100)}.wav`;
    }
    
    if(status) status.textContent = `Custom mix ready! Vocal ${Math.round(vocalGain*100)}% Track ${Math.round(accGain*100)}% Master ${Math.round(masterGain*100)}%`;
    
    // Also offer client-side WAV download as fallback
    if(window._lastMixedWavBlob){
      const clientUrl = URL.createObjectURL(window._lastMixedWavBlob);
      log('Client-side WAV also available: ' + clientUrl.slice(0,60));
    }
    
  } catch(e) {
    log('Custom mix failed: ' + e.message);
    if(status) status.textContent = 'Custom mix failed: ' + e.message;
    showError('Custom mix failed: ' + e.message);
  }
}

function showResult(job) {
  const resultCard = el('resultCard');
  if(resultCard) resultCard.classList.remove('hidden');
  const files = job.files || {};
  const resultMeta = el('resultMeta');
  if(resultMeta) resultMeta.textContent = `${job.analysis?.key || ''} • ${job.analysis?.bpm || ''} BPM • ${job.analysis?.duration_sec || ''}s • ${job.style} • v1.6 REAL PIANO + MIXER`;

  const finalAudio = el('finalAudio');
  if(finalAudio && files.mp3){
    finalAudio.src = files.mp3;
  }
  const dlMp3 = el('dlMp3');
  if(dlMp3 && files.mp3){
    dlMp3.href = files.mp3;
  }
  const dlWav = el('dlWav');
  if(dlWav && files.wav){
    dlWav.href = files.wav;
  }
  const vocalAudio = el('vocalAudio');
  if(vocalAudio && files.vocal){
    vocalAudio.src = files.vocal;
  }
  const accAudio = el('accAudio');
  if(accAudio && files.accompaniment){
    accAudio.src = files.accompaniment;
  }
  const dlVocal = el('dlVocal');
  if(dlVocal && files.vocal){
    dlVocal.href = files.vocal;
  }
  const dlAcc = el('dlAcc');
  if(dlAcc && files.accompaniment){
    dlAcc.href = files.accompaniment;
  }
  const lyricsBox = el('lyricsBox');
  const lyricsText = el('lyricsText');
  if(job.analysis?.lyrics_preview && lyricsBox && lyricsText){
    lyricsBox.classList.remove('hidden');
    lyricsText.textContent = job.analysis.lyrics_preview;
  }
  
  // Init volume mixer with stems
  if(files.vocal && files.accompaniment){
    log('Initializing volume mixer with stems...');
    // Small delay to ensure audio elements loaded
    setTimeout(() => {
      initVolumeMixer(files.vocal, files.accompaniment);
    }, 500);
  } else {
    log('No vocal/accompaniment stems for mixer, only final mix available');
  }
  
  if(resultCard) resultCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function loadJobs(){
  try{
    const res = await fetch('/api/jobs?limit=10');
    if(!res.ok) throw new Error('failed ' + res.status);
    const data = await res.json();
    const list = el('jobsList');
    if(!list) return;
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
        const progressCard = el('progressCard');
        if(progressCard) progressCard.classList.remove('hidden');
        if(j.status==='completed') showResult(j);
        else pollJob(j.job_id);
      };
      list.appendChild(div);
    });
  }catch(e){
    const list = el('jobsList');
    if(list) list.textContent = 'Failed to load: ' + e.message;
    log('loadJobs failed: ' + e.message);
  }
}

async function toggleRecord(){
  const btn = el('recBtn');
  const status = el('recStatus');
  const hint = el('recHint');
  if(mediaRecorder && mediaRecorder.state === 'recording'){
    mediaRecorder.stop();
    if(btn){
      btn.textContent = '●';
      btn.className = 'w-14 h-14 rounded-full bg-gradient-to-br from-red-500 to-pink-500 text-white text-xl flex items-center justify-center shadow-lg hover:scale-105 transition';
    }
    if(status){
      status.textContent = 'processing';
      status.className = 'text-[10px] mono px-2 py-1 rounded-full bg-zinc-100';
    }
    clearInterval(recTimerInterval);
    log('Recording stopped');
    return;
  }

  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
    showError('Recording not supported in this browser/iframe. Please use upload instead, or open preview in new tab (pop-out icon).');
    log('mediaDevices not available');
    return;
  }

  try{
    log('Requesting microphone...');
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation:true, noiseSuppression:true } });
    log('Microphone granted');
    recChunks = [];
    let mimeType = 'audio/webm';
    if(MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) mimeType = 'audio/webm;codecs=opus';
    else if(MediaRecorder.isTypeSupported('audio/webm')) mimeType = 'audio/webm';
    else if(MediaRecorder.isTypeSupported('audio/mp4')) mimeType = 'audio/mp4';
    log('Using mimeType: ' + mimeType);
    mediaRecorder = new MediaRecorder(stream, { mimeType });
    mediaRecorder.ondataavailable = e=>{ if(e.data.size>0) recChunks.push(e.data); log(`Chunk ${e.data.size} bytes`); };
    mediaRecorder.onerror = e=>{ showError('Recorder error: ' + e.error); log('Recorder error: ' + e.error); };
    mediaRecorder.onstop = ()=>{
      const blob = new Blob(recChunks, { type: mediaRecorder.mimeType });
      const url = URL.createObjectURL(blob);
      const preview = el('recPreview');
      if(preview){
        preview.src = url;
        preview.classList.remove('hidden');
      }
      const file = new File([blob], `recording_${Date.now()}.webm`, { type: blob.type });
      setFile(file, file.name);
      if(status){
        status.textContent = 'ready';
      }
      if(hint){
        hint.textContent = 'Recording ready — hit Generate!';
      }
      stream.getTracks().forEach(t=>t.stop());
      log(`Recording blob ${blob.size} bytes ready`);
    };
    mediaRecorder.start(100);
    recStartTime = Date.now();
    if(btn){
      btn.textContent = '■';
      btn.className = 'w-14 h-14 rounded-full bg-zinc-900 text-white text-xl flex items-center justify-center shadow-lg animate-pulse';
    }
    if(status){
      status.textContent = 'recording';
      status.className = 'text-[10px] mono px-2 py-1 rounded-full bg-red-100 text-red-600';
    }
    if(hint){
      hint.textContent = 'Recording... sing now!';
    }

    recTimerInterval = setInterval(()=>{
      const elapsed = Math.floor((Date.now()-recStartTime)/1000);
      const mm = String(Math.floor(elapsed/60)).padStart(2,'0');
      const ss = String(elapsed%60).padStart(2,'0');
      const timer = el('recTimer');
      if(timer) timer.textContent = `${mm}:${ss}`;
    }, 500);

    try{
      const audioCtxLocal = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtxLocal.createMediaStreamSource(stream);
      const analyser = audioCtxLocal.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const barsContainer = el('liveBars');
      const bars = barsContainer ? barsContainer.children : [];
      const loop = ()=>{
        if(!mediaRecorder || mediaRecorder.state !== 'recording'){ try{audioCtxLocal.close();}catch{} return; }
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
    const msg = e.name === 'NotAllowedError' ? 'Microphone permission denied. Please allow mic and try again. In Arena preview iframe, you may need to open in new tab (pop-out icon at top right of preview).' : e.message;
    showError('Microphone error: ' + msg);
    log('getUserMedia failed: ' + e.name + ' ' + e.message);
    const recStatus = el('recStatus');
    if(recStatus) recStatus.textContent = 'blocked';
    const recHint = el('recHint');
    if(recHint) recHint.textContent = 'Mic blocked — use upload or open preview in new tab.';
  }
}

function setupUploadHandlers(){
  const drop = el('dropZone');
  const fileInput = el('fileInput');
  const fallbackInput = el('fileInputFallback');
  const browseBtn = el('browseBtn');

  log('Setting up upload handlers...');

  const openPicker = (e) => {
    if(e){
      e.preventDefault();
      e.stopPropagation();
    }
    log('Browse clicked, opening file picker');
    if(fileInput){
      fileInput.click();
    } else {
      log('fileInput not found!');
      showError('File input not found — try fallback upload at /test-upload');
    }
  };

  if(drop){
    drop.addEventListener('click', openPicker);
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
      log(`Drop: ${f?f.name + ' ' + f.size + ' ' + f.type:'no file'}`);
      if(f){
        if(!f.type.startsWith('audio/') && !f.type.startsWith('video/') && !/\.(mp3|wav|m4a|mp4|webm|ogg|flac|mov|aac|opus)$/i.test(f.name)){
          showError(`Unsupported file type: ${f.type||f.name}. Try MP3, WAV, M4A, MP4, WebM.`);
          return;
        }
        setFile(f, f.name);
      }
    });
    log('Drop zone handlers attached');
  }

  if(browseBtn){
    browseBtn.addEventListener('click', openPicker);
    log('browseBtn handler attached');
  }

  if(fileInput){
    fileInput.addEventListener('change', ()=>{
      log(`File input change: ${fileInput.files.length} files`);
      if(fileInput.files && fileInput.files[0]){
        const f = fileInput.files[0];
        log(`Selected: ${f.name} ${f.size} ${f.type}`);
        setFile(f, f.name);
      }
    });
    log('fileInput change handler attached');
  }

  if(fallbackInput){
    fallbackInput.addEventListener('change', ()=>{
      log(`Fallback input change: ${fallbackInput.files.length} files`);
      if(fallbackInput.files && fallbackInput.files[0]){
        setFile(fallbackInput.files[0], fallbackInput.files[0].name);
      }
    });
  }

  const clearBtn = el('clearFile');
  if(clearBtn){
    clearBtn.onclick = clearFile;
  }

  const genBtn = el('generateBtn');
  if(genBtn){
    genBtn.onclick = uploadAndGenerate;
    log('Generate button handler attached');
  }

  const recBtn = el('recBtn');
  if(recBtn){
    recBtn.onclick = toggleRecord;
  }

  const refreshBtn = el('refreshJobs');
  if(refreshBtn){
    refreshBtn.onclick = loadJobs;
  }

  const newSongBtn = el('newSongBtn');
  if(newSongBtn){
    newSongBtn.onclick = ()=>{
      clearFile();
      const progressCard = el('progressCard');
      if(progressCard) progressCard.classList.add('hidden');
      const resultCard = el('resultCard');
      if(resultCard) resultCard.classList.add('hidden');
      hideError();
      // Stop mixer
      if(currentSources){
        currentSources.forEach(src => { try{src.stop();}catch{} });
        currentSources = [];
      }
      if(audioCtx){
        try{audioCtx.close();}catch{}
        audioCtx = null;
      }
      isMixerReady = false;
      window.scrollTo({ top:0, behavior:'smooth' });
    };
  }

  const shareBtn = el('shareBtn');
  if(shareBtn){
    shareBtn.onclick = ()=>{
      if(!currentJobId) return;
      const url = `${location.origin}/api/jobs/${currentJobId}/files/final.mp3`;
      if(navigator.share){
        navigator.share({ title: 'My SingSmith song', url }).catch(()=>{});
      } else {
        navigator.clipboard.writeText(url).then(()=>alert('Link copied: ' + url)).catch(()=>alert(url));
      }
    };
  }

  const renderCustomBtn = el('renderCustomMixBtn');
  if(renderCustomBtn){
    renderCustomBtn.onclick = renderCustomMixOnServer;
    log('Custom mix button handler attached');
  }

  log('All upload handlers setup done');
}

document.addEventListener('DOMContentLoaded', ()=>{
  log(`Frontend v1.6 loaded. Origin: ${location.origin} Host: ${location.host} Protocol: ${location.protocol} UserAgent: ${navigator.userAgent.slice(0,100)}`);
  const originInfo = el('originInfo');
  if(originInfo){
    originInfo.textContent = `Origin: ${location.origin} | v1.6 REAL PIANO + VOLUME MIXER | If recording fails, open this URL in new tab and allow mic.`;
  }

  initStylePicker();
  initLiveBars();
  loadJobs();
  setupUploadHandlers();

  fetch('/api/health').then(r=>r.json()).then(j=>{
    log('API health: ' + JSON.stringify(j));
  }).catch(e=>{ 
    showError('API not reachable: ' + e.message + ' — backend may not be running. Run: python -m uvicorn api.main:app --host 0.0.0.0 --port 8000'); 
    log('Health check failed: ' + e.message);
  });

  const fileInput = el('fileInput');
  if(fileInput){
    log('File input element found, accept=' + fileInput.accept);
  } else {
    log('CRITICAL: fileInput element NOT found in DOM!');
    showError('Upload input not found — try /test-upload fallback or reload page');
  }
});
