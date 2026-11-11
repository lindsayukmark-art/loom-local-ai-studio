'use strict';

const $ = (selector, scope = document) => scope.querySelector(selector);
const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
const NS = 'http://www.w3.org/2000/svg';
const PATHS = {
  sparkles: ['M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2L12 3Z', 'M20 3v4M18 5h4'],
  image: ['M4 3h16a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z', 'm3 16 5-5 6 6 3-3 4 4', 'M15 7h.01'],
  video: ['M4 5h11a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Z', 'm16 9 5-3v12l-5-3'],
  audio: ['M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4'],
  mic: ['M12 15a3 3 0 0 0 3-3V5a3 3 0 0 0-6 0v7a3 3 0 0 0 3 3Z', 'M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8'],
  game: ['M7 7h10c2 0 3 2 3.5 4l1 6c.5 3-2 4-4 2l-2-2h-7l-2 2c-2 2-4.5 1-4-2l1-6C4 9 5 7 7 7Z', 'M7 10v5M4.5 12.5h5M16 11h.01M19 14h.01'],
  grid: ['M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z'],
  brain: ['M12 4v16M12 5C8 1 5 4 5 7c-4 0-4 7-1 8-2 4 3 7 6 4 1 2 2 1 2 1M12 5c4-4 7-1 7 2 4 0 4 7 1 8 2 4-3 7-6 4-1 2-2 1-2 1', 'M5 7c0 3 3 3 3 3M19 7c0 3-3 3-3 3M4 15c2-2 4-1 4 1M20 15c-2-2-4-1-4 1'],
  agents: ['M12 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M5 20a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM19 20a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M12 8v3M5 14v-3h14v3'],
  lock: ['M5 10h14v11H5z', 'M8 10V7a4 4 0 0 1 8 0v3M12 14v3'],
  shield: ['m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4Z', 'm8 12 3 3 5-6'],
  settings: ['m10 2 4 0 1 3 3 1 3 0 1 4-2 2 0 3 2 2-2 4-3-1-3 2-1 3h-4l-1-3-3-1-3 0-1-4 2-2 0-3-2-2 2-4 3 1 3-2 1-3Z', 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z'],
  sliders: ['M4 3v8M4 15v6M12 3v3M12 10v11M20 3v11M20 18v3', 'M1 11h6v4H1zM9 6h6v4H9zM17 14h6v4h-6z'],
  'arrow-up-right': ['M6 18 18 6M6 6h12v12'],
  'arrow-right': ['M4 12h16m-6-6 6 6-6 6'],
  upload: ['M12 16V3m-5 5 5-5 5 5', 'M4 15v6h16v-6'],
  download: ['M12 3v13m-5-5 5 5 5-5', 'M4 16v5h16v-5'],
  info: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M12 11v6M12 7h.01'],
  layers: ['m12 3 10 5-10 5L2 8l10-5Z', 'm2 12 10 5 10-5M2 16l10 5 10-5'],
  plus: ['M12 4v16M4 12h16'],
  check: ['m5 12 4 4L19 6'],
  trash: ['M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7'],
  sprout: ['M12 21v-9M12 13C4 14 2 8 3 4c5-1 10 3 9 9ZM12 16c0-7 4-10 9-9 1 5-3 10-9 9Z'],
  refresh: ['M20 7a8 8 0 0 0-13-2L3 9M3 3v6h6M4 17a8 8 0 0 0 13 2l4-4M21 21v-6h-6'],
  menu: ['M3 5h18M3 12h18M3 19h18'],
  folder: ['M2 6h8l2 3h10l-2 12H3L2 6ZM2 6V3h8l2 3h8v3'],
  thumbs: ['M7 10 11 3c1-1 3-1 3 2l-1 5h7l1 2-3 9H7V10ZM3 10h4v11H3z'],
  flag: ['M4 22V3m0 1c6-4 10 4 16 0v12c-6 4-10-4-16 0'],
  play: ['m8 4 12 8-12 8V4Z'],
};

function icon(name) {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  (PATHS[name] || PATHS.sparkles).forEach(d => { const path = document.createElementNS(NS, 'path'); path.setAttribute('d', d); svg.append(path); });
  return svg;
}
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, String(value));
  }
  children.flat(Infinity).filter(child => child !== null && child !== undefined).forEach(child => node.append(child instanceof Node ? child : document.createTextNode(String(child))));
  return node;
}
function decorateIcons(scope = document) { $$('[data-icon]', scope).forEach(node => node.replaceChildren(icon(node.dataset.icon))); }
function empty(title, text, symbol = 'layers') { return el('div', {class:'empty-state'}, el('div', {class:'empty-icon'}, icon(symbol)), el('h3', {}, title), el('p', {}, text)); }
function fileURL(url) { return typeof url === 'string' && url.startsWith('/api/assets/') && !url.includes('\\') && !url.includes('#') ? url : null; }
function viewableImage(asset) { return asset.kind === 'image' && asset.mime !== 'image/tiff'; }
function dateLabel(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(undefined, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}).format(date); }
function timeLabel(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(undefined, {hour:'2-digit', minute:'2-digit'}).format(date); }
function kindIcon(kind) { return ({task:'sparkles',image:'image',video:'video',edit:'sliders',audio:'audio',voice:'mic',animation:'layers',game:'game'})[kind] || 'layers'; }
const state = {kind:'auto', view:'studio', status:null, jobs:[], assets:[], memories:[], busy:false, uploadBusy:false, feedback:new Set(), fingerprints:new Map()};
let toastTimer;
function toast(message, error = false) { const node = $('#toast'); clearTimeout(toastTimer); node.textContent = message; node.classList.toggle('error',error); node.hidden = false; toastTimer = setTimeout(() => {node.hidden = true;}, 5000); }
function inlineError(id, error = '') { const node = $(id); node.textContent = error; node.hidden = !error; }
async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeout || 45000);
  const opts = {...options, signal:controller.signal, credentials:'same-origin'};
  delete opts.timeout;
  if (options.body && !(options.body instanceof FormData)) { opts.headers = {...options.headers, 'Content-Type':'application/json'}; opts.body = JSON.stringify(options.body); }
  try {
    const response = await fetch(path, opts);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('; ') : data.error;
      throw new Error(detail || `The local app returned ${response.status}. Please try again.`);
    }
    return data;
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('The local app took too long to respond. Check that Loom is still running.');
    if (error instanceof TypeError) throw new Error('Cannot reach the local app. Check that Loom is running, then try again.');
    throw error;
  } finally { clearTimeout(timer); }
}
function navigate(view) {
  if (!['studio','library','memory','agents','settings'].includes(view)) view = 'studio';
  state.view = view;
  $$('.view').forEach(node => { const active = node.id === `view-${view}`; node.hidden = !active; node.classList.toggle('active',active); });
  $$('.nav-item[data-view]').forEach(node => { node.classList.toggle('active',node.dataset.view === view); if(node.dataset.view === view) node.setAttribute('aria-current','page'); else node.removeAttribute('aria-current'); });
  $('#page-title').textContent = ({studio:'Studio',library:'Library',memory:'Memory',agents:'Agents',settings:'Settings & models'})[view];
  $('.sidebar').classList.remove('open');
  history.replaceState(null,'',`#${view}`);
  if(view === 'memory') loadMemories().catch(error => toast(error.message,true));
  if(view === 'library') loadAssets().catch(error => toast(error.message,true));
  if(view === 'settings') loadSettings().catch(error => toast(error.message,true));
}

function selectedAsset() { return state.assets.find(asset => asset.id === $('#asset-select').value) || null; }
function setKind(kind) {
  state.kind = kind;
  $$('.composer-tab').forEach(node => { const active = node.dataset.kind === kind; node.classList.toggle('active',active); node.setAttribute('aria-selected',String(active)); node.tabIndex = active ? 0 : -1; });
  const labels = {auto:['What are we making today?','Describe your idea. Let your agents choose a workflow…'],task:['What are we making today?','Plan a short film about an ordinary day that feels extraordinary…'],image:['Describe the image you imagine.','A quiet mountain lake at dawn, soft mist, warm film tones…'],video:['Make a moment move.','Describe a video, or upload an image to animate it locally…'],edit:['Give your source material a new perspective.','Describe this edit for your workspace history…'],audio:['Give your sound some breathing room.','Clean up the background noise in this recording…'],voice:['Give an idea a voice.','Paste the words to speak with your local Piper voice model, or choose a recording for voice effects…'],animation:['A little movement for your live stream.','Describe your overlay for your workspace history. Upload a transparent image to animate…'],game:['What would you like to play?','Create a space shooter with stars, a score, and a restart button…']};
  $('#prompt-label').textContent = labels[kind][0];
  $('#prompt').placeholder = labels[kind][1];
  $('#prompt').required = ['auto','task','image','game'].includes(kind);
  renderAssetSelect(); updateComposer();
}
function updateComposer() {
  const kind = state.kind;
  const asset = selectedAsset();
  const imageEdit = kind === 'edit' && (!asset || asset.kind === 'image');
  const videoEdit = kind === 'edit' && asset?.kind === 'video';
  const audioEdit = kind === 'audio' || (kind === 'edit' && asset?.kind === 'audio');
  $('#asset-controls').hidden = !['auto','image','video','edit','audio','voice','animation'].includes(kind);
  $('#prompt').required = ['auto','task','image','game'].includes(kind) || (kind === 'voice' && !asset);
  $('#edit-controls').hidden = !imageEdit;
  $('#image-controls').hidden = kind !== 'image';
  $('#video-controls').hidden = !(kind === 'video' || videoEdit);
  $('#video-audio-controls').hidden = !(videoEdit || (kind === 'video' && asset?.kind === 'video'));
  $('#audio-controls').hidden = !audioEdit;
  $('#voice-controls').hidden = !(kind === 'voice' && asset);
  $('#overlay-controls').hidden = kind !== 'animation';
  const operation = $('#edit-operation').value;
  $$('.edit-size').forEach(node => {node.hidden = !['resize','crop'].includes(operation);});
  $('#angle-control').hidden = operation !== 'rotate';
  $('#factor-control').hidden = !['brightness','contrast','sharpen'].includes(operation);
  $('#edit-factor').max = operation === 'sharpen' ? '5' : '3';
  const providers = state.status?.providers || {};
  let message, warning = false;
  if (kind === 'auto') {
    const anyModel = Object.values(providers).some(provider => provider?.available);
    message = anyModel ? 'The local router chooses a workflow from your request. It learns from explicit task choices and feedback. Choose a tab for detailed media controls.' : 'No AI models connected yet. Local media edits, voice effects, and game templates work now. Set up models for AI generation. The local router chooses a workflow from your request.';
    warning = !anyModel;
  } else if (kind === 'task') {
    message = providers.reasoning?.available ? 'Your installed language model will plan, create, and review this work locally.' : 'No language model connected. You can save a task-brief template, or connect Ollama in Settings.';
    warning = !providers.reasoning?.available;
  } else if (kind === 'image') {
    message = providers.image?.available ? 'Generates with your local image pipeline. An uploaded image can provide inspiration.' : 'Image generation needs local model files and GPU dependencies. Connect an image model in Settings.';
    warning = !providers.image?.available;
  } else if (kind === 'animation') {
    message = 'Creates an alpha-transparent OBS overlay with local animation tools. Use a transparent PNG or remove a chosen solid background colour. No AI model needed.';
  } else if (kind === 'voice') {
    message = asset ? 'Changes pitch and speed using local audio effects. This does not clone a voice or train a new voice model.' : providers.voice?.available ? 'Turns your script into speech using your installed local Piper voice model.' : 'Choose a recording for local pitch/speed effects, or configure a Piper .onnx voice model in Settings for text-to-speech.';
    warning = !asset && !providers.voice?.available;
  } else if (kind === 'game') {
    message = providers.reasoning?.available ? 'Creates a playable HTML5 game with your local model, plus a Windows-ready project ZIP. Review gameplay after creation.' : 'No language model connected. Creates a built-in Snake or Space Shooter game, playable here or on Windows from the project ZIP.';
  } else if (audioEdit) {
    message = 'Local FFmpeg noise reduction and loudness normalization. Upload audio or a video to extract and clean its sound. This is filter-based cleanup.';
  } else if (videoEdit || (kind === 'video' && asset)) {
    message = asset?.kind === 'image' ? 'Turns your image into a gentle zoom animation using local FFmpeg. No video AI model needed.' : 'Trims, resizes, and optionally cleans the sound of your uploaded video with local FFmpeg.';
  } else if (kind === 'video') {
    message = providers.video?.available ? 'Generates a short video with your local model, or upload an image for a lightweight animation.' : 'Upload an image for a local animation, or a video to edit. Generative video requires a supported local model.';
    warning = !providers.video?.available;
  } else { message = 'Choose a source image, video, or audio file. Edits use local media tools and do not need AI model files.'; }
  const notice = $('#capability-notice'); notice.replaceChildren(icon('info'),el('span',{},message)); notice.classList.toggle('warning',warning);
}
function renderAssetSelect() {
  const node = $('#asset-select'); const previous = node.value;
  const allowed = ['image','animation'].includes(state.kind) ? ['image'] : state.kind === 'video' ? ['image','video'] : ['audio','voice'].includes(state.kind) ? ['audio','video'] : ['image','video','audio'];
  node.replaceChildren(el('option',{value:''}, state.kind === 'image' ? 'Optional inspiration image' : state.kind === 'video' ? 'Choose source, or generate with a model' : state.kind === 'voice' ? 'Speak the script, or choose a recording for effects' : 'Choose source media'));
  state.assets.filter(asset => allowed.includes(asset.kind)).forEach(asset => node.append(el('option',{value:asset.id},`${asset.name} · ${asset.kind}`)));
  if([...node.options].some(option => option.value === previous)) node.value = previous;
}

function agentStyle(id) { return ({planner:['sparkles',''],memory:['brain','lilac'],creator:['image','blue'],editor:['sliders','peach'],developer:['game','teal'],reviewer:['shield','teal'],learner:['sprout','lilac']})[id] || ['agents','']; }
function renderAgents() {
  const agents = state.status?.agents || [];
  const descriptions = {planner:'A thoughtful place to start',memory:'Remembers what matters',creator:'Makes the idea tangible',editor:'Finds the finishing touch',developer:'Makes room for play',reviewer:'A second pair of eyes',learner:'Learns from your feedback'};
  $('#team-list').replaceChildren(...agents.map(agent => { const [symbol,color] = agentStyle(agent.id); return el('div',{class:'team-member'},el('span',{class:`agent-avatar ${color}`},icon(symbol)),el('div',{},el('strong',{},agent.name),el('p',{},descriptions[agent.id] || agent.role)),el('span',{class:'status-dot'})); }));
  $('#agents-grid').replaceChildren(...agents.map(agent => { const [symbol,color] = agentStyle(agent.id); return el('article',{class:'card agent-detail'},el('span',{class:`agent-avatar ${color}`},icon(symbol)),el('h2',{},agent.name),el('p',{},agent.role),el('span',{class:'mini-pill'},'LOCAL WORKFLOW')); }));
}
function renderStats(stats = {}) {
  $('#memory-summary').textContent = `${stats.memory_count || 0} saved preferences`;
  $('#learning-stats').replaceChildren(...[['memory_count','Preferences'],['feedback_count','Feedback entries'],['route_examples','Route examples']].map(([key,label]) => el('div',{class:'learning-stat'},el('strong',{},stats[key] || 0),el('span',{},label))));
}
function renderProviders() {
  const providers = state.status?.providers || {};
  $('#providers-list').replaceChildren(...[['reasoning','Language & reasoning','sparkles'],['image','Image generation','image'],['video','Video generation','video'],['voice','Voice & speech','mic']].map(([key,title,symbol]) => {
    const provider = providers[key] || {};
    return el('article',{class:'card provider-card'},el('div',{class:'section-heading'},el('h2',{},title),el('span',{class:`provider-status ${provider.available ? '' : 'unavailable'}`},el('span',{class:'status-dot'}),provider.available ? 'Ready' : 'Not connected')),el('p',{},provider.label || 'Local model'),el('small',{},provider.detail || 'Check local model settings.'));
  }));
  if(state.status?.hardware_hint) $('#hardware-hint').textContent = state.status.hardware_hint;
}
async function loadStatus() {
  try {
    state.status = await api('/api/status');
    $('#connection-text').textContent = 'Running locally';
    $('#connection-dot').classList.remove('error','warning');
    $('#global-error').hidden = true;
    renderAgents(); renderProviders(); renderStats(state.status.learning); updateComposer();
  } catch(error) {
    $('#connection-text').textContent = 'App unavailable'; $('#connection-dot').classList.add('error');
    const banner = $('#global-error'); banner.textContent = error.message; banner.hidden = false;
    throw error;
  }
}

function artifactNode(artifact) {
  const url = fileURL(artifact.url); if(!url) return null;
  const download = el('a',{href:url,download:artifact.name || 'download'},icon('download'),'Save');
  let media;
  if(viewableImage(artifact)) media = el('img',{src:url,alt:artifact.name || 'Generated image',loading:'lazy'});
  else if(artifact.kind === 'video') media = el('video',{src:url,controls:true,preload:'metadata',playsinline:true});
  else if(artifact.kind === 'audio') media = el('div',{class:'audio-preview'},el('div',{},icon('audio')),el('audio',{src:url,controls:true,preload:'metadata'}));
  else if(artifact.kind === 'game') {
    media = el('div',{class:'game-preview'});
    const start = el('button',{type:'button',class:'game-start'},icon('play'),el('strong',{},'Play your game'),el('span',{},'Runs in an isolated local preview'));
    start.addEventListener('click',() => { const frame = el('iframe',{src:url,title:artifact.name || 'Playable game',sandbox:'allow-scripts',referrerpolicy:'no-referrer',class:'game-frame'}); media.replaceChildren(frame); });
    media.append(start);
  } else media = el('div',{class:'file-preview'},icon(artifact.kind === 'archive' ? 'folder' : 'layers'),el('span',{},artifact.kind === 'archive' ? 'Project ZIP · includes Windows launcher' : artifact.kind === 'image' ? 'TIFF image · save to view' : 'Local document'));
  return el('figure',{class:'artifact'},media,el('figcaption',{},el('span',{},artifact.name || artifact.kind),download));
}
function feedbackForm(job) {
  const wrapper = el('div',{class:'feedback-wrapper'});
  if(state.feedback.has(job.id)) return el('div',{class:'feedback-saved'},'Feedback saved locally. Thank you.');
  const toggle = el('button',{class:'feedback-toggle',type:'button','aria-expanded':'false'},icon('sprout'),'Teach your agents something from this result');
  const form = el('form',{class:'feedback-form',hidden:true});
  let rating = 1;
  const good = el('button',{class:'rating-button active',type:'button','aria-pressed':'true'},icon('thumbs'),'Useful');
  const bad = el('button',{class:'rating-button',type:'button','aria-pressed':'false'},icon('flag'),'Needs work');
  function choose(value) {rating = value; good.classList.toggle('active',value === 1); bad.classList.toggle('active',value === -1); good.setAttribute('aria-pressed',String(value === 1)); bad.setAttribute('aria-pressed',String(value === -1));}
  good.addEventListener('click',() => choose(1)); bad.addEventListener('click',() => choose(-1));
  const note = el('textarea',{rows:'2',maxlength:'2000',placeholder:'What worked, or what should change?','aria-label':'Feedback note'});
  const remember = el('input',{type:'checkbox'});
  const route = el('select',{'aria-label':'Correct workflow'}); route.append(el('option',{value:''},'Workflow was correct')); ['task','image','video','edit','audio','voice','animation','game'].forEach(kind => route.append(el('option',{value:kind},`Should use ${kind}`)));
  const save = el('button',{type:'submit',class:'primary-button'},'Save feedback',icon('check'));
  const error = el('p',{class:'inline-error',role:'alert',hidden:true});
  form.append(el('div',{class:'feedback-actions'},good,bad),note,el('label',{class:'check-label feedback-remember'},remember,'Remember this note as a preference (useful results only)'),el('div',{class:'feedback-controls'},route,save),error);
  toggle.addEventListener('click',() => { form.hidden = !form.hidden; toggle.setAttribute('aria-expanded',String(!form.hidden)); if(!form.hidden) note.focus(); });
  form.addEventListener('submit',async event => {
    event.preventDefault(); error.hidden = true;
    if(remember.checked && (!note.value.trim() || rating !== 1)) { error.textContent = 'To remember a preference, choose Useful and add a specific note.'; error.hidden = false; return; }
    save.disabled = true;
    try { await api(`/api/jobs/${encodeURIComponent(job.id)}/feedback`,{method:'POST',body:{rating,note:note.value.trim(),remember:remember.checked,correct_kind:route.value || null}}); state.feedback.add(job.id); wrapper.replaceChildren(el('div',{class:'feedback-saved'},'Feedback saved locally.')); loadStatus().catch(() => {}); }
    catch(err) { error.textContent = err.message; error.hidden = false; save.disabled = false; }
  });
  wrapper.append(toggle,form); return wrapper;
}
function jobNode(job) {
  const node = el('article',{class:'job-card','data-job-id':job.id});
  const names = new Map((state.status?.agents || []).map(agent => [agent.id,agent.name]));
  const header = el('div',{class:'job-header'},el('span',{class:'job-kind-icon'},icon(kindIcon(job.kind))),el('div',{class:'job-header-content'},el('h3',{},job.prompt),el('div',{class:'job-meta'},el('span',{},`${job.kind.charAt(0).toUpperCase()}${job.kind.slice(1)}`),el('span',{},'·'),el('time',{datetime:job.created_at},dateLabel(job.created_at)))),el('span',{class:`job-status ${job.status}`},job.status.charAt(0).toUpperCase()+job.status.slice(1)));
  node.append(header);
  if(['queued','running'].includes(job.status)) node.append(el('progress',{class:'job-progress','aria-label':'Job progress',value:Math.min(100,Math.max(0,Number(job.progress) || 0)),max:100}));
  if(job.events?.length) {
    const details = el('details',{class:'events-details'});
    const summary = el('summary',{},`${job.events.length} agent updates`,el('span',{},'View activity'));
    if(['queued','running'].includes(job.status)) details.open = true;
    details.append(summary,el('div',{class:'job-events'},job.events.map(event => el('div',{class:'job-event'},el('span',{class:'event-dot'},event.status === 'running' ? '·' : '✓'),el('div',{},el('strong',{},`${names.get(event.agent) || event.agent} · `),event.message),el('time',{datetime:event.at},timeLabel(event.at))))));
    node.append(details);
  }
  if(job.error) node.append(el('div',{class:'job-error',role:'status'},job.error));
  if(job.result) {
    const mode = ({template:'Template · no language model',local_tools:'Local media tools',local_model:'Local AI model'})[job.result.mode] || job.result.mode;
    if(mode) node.append(el('span',{class:'mode-label'},icon('lock'),mode));
    if(job.result.text) node.append(el('div',{class:'job-output'},job.result.text));
    if(job.result.artifacts?.length) node.append(el('div',{class:'job-artifacts'},job.result.artifacts.map(artifactNode)));
  }
  if(job.status === 'completed') node.append(feedbackForm(job));
  return node;
}
function renderJobs() {
  $('#job-count').textContent = `${state.jobs.length} ${state.jobs.length === 1 ? 'creation' : 'creations'}`;
  const list = $('#jobs-list');
  if(!state.jobs.length) { if(!$('.empty-state',list)) list.replaceChildren(empty('Every good thing starts somewhere.','Your creations and agent activity will appear here. Start with an idea above, or try a local media edit.')); return; }
  $('.empty-state',list)?.remove();
  const shown = state.jobs.slice(0,40);
  shown.forEach((job,index) => {
    const fingerprint = JSON.stringify(job);
    let existing = [...list.children].find(node => node.dataset.jobId === job.id);
    if(!existing || (state.fingerprints.get(job.id) !== fingerprint && !existing.contains(document.activeElement))) { const replacement = jobNode(job); if(existing) existing.replaceWith(replacement); existing = replacement; state.fingerprints.set(job.id,fingerprint); }
    if(list.children[index] !== existing) list.insertBefore(existing,list.children[index] || null);
  });
  [...list.children].filter(node => !shown.some(job => job.id === node.dataset.jobId)).forEach(node => node.remove());
}
async function loadJobs() { const data = await api('/api/jobs'); state.jobs = data.jobs || []; renderJobs(); }
function renderAssets() {
  $('#library-count').textContent = state.assets.length;
  $('#asset-total').textContent = `${state.assets.length} ${state.assets.length === 1 ? 'file' : 'files'}`;
  const grid = $('#assets-grid');
  if(!state.assets.length) {grid.replaceChildren(empty('A little room for inspiration.','Upload an image, a video, or an audio recording to start your collection.','image'));return;}
  grid.replaceChildren(...state.assets.map(asset => {
    const url = fileURL(asset.url); if(!url) return null;
    let preview;
    if(viewableImage(asset)) preview = el('img',{src:url,alt:asset.name,loading:'lazy'});
    else if(asset.kind === 'video') preview = el('video',{src:url,controls:true,preload:'metadata',playsinline:true});
    else preview = el('div',{class:'library-file-preview'},icon(asset.kind === 'audio' ? 'audio' : asset.kind === 'game' ? 'game' : 'folder'),el('span',{},asset.kind));
    const meta = [asset.kind]; if(asset.width && asset.height) meta.push(`${asset.width} × ${asset.height}`); if(asset.duration) meta.push(`${Number(asset.duration).toFixed(1)} sec`);
    const actions = el('div',{class:'media-card-actions'});
    if(['image','video','audio'].includes(asset.kind)) actions.append(el('button',{type:'button',onclick:() => {setKind(asset.kind === 'audio' ? 'audio' : 'edit'); $('#asset-select').value = asset.id; updateComposer(); navigate('studio'); $('#prompt').focus();}},icon('sliders'),'Use in studio'));
    actions.append(el('a',{href:url,download:asset.name},icon('download'),'Save'));
    const info = el('div',{class:'media-card-info'},el('h3',{title:asset.name},asset.name),el('p',{},meta.join(' · ')),actions);
    if(['image','video','audio'].includes(asset.kind)) {
      const formats = {image:['png','jpg','webp','gif','bmp','tiff'],audio:['mp3','wav','flac','ogg','m4a'],video:['mp4','webm','mov']}[asset.kind];
      const format = el('select',{'aria-label':`Export format for ${asset.name}`},formats.map(value => el('option',{value},value.toUpperCase())));
      const exportButton = el('button',{class:'secondary-button',type:'button'},icon('download'),'Export');
      const note = el('p',{class:'export-note'},asset.kind === 'image' ? 'JPG flattens transparency. PNG preserves alpha.' : asset.kind === 'video' ? 'MP4 / MOV flatten alpha. Use Overlay for OBS transparency.' : 'Convert locally. Lossy formats can reduce sound quality.');
      exportButton.addEventListener('click',async () => {
        exportButton.disabled = true;
        try {const job = await api('/api/jobs',{method:'POST',body:{kind:'edit',asset_id:asset.id,prompt:`Export ${asset.name} as ${format.value.toUpperCase()}`,options:{operation:'export',format:format.value},use_memory:false}});state.jobs.unshift(job);renderJobs();navigate('studio');toast('Export added to your local workspace.');}
        catch(error){toast(error.message,true);}finally{exportButton.disabled = false;}
      });
      info.append(el('div',{class:'media-export'},format,exportButton),note);
    }
    return el('article',{class:'media-card'},el('div',{class:'media-preview'},preview),info);
  }).filter(Boolean));
}
async function loadAssets() {const previous = $('#asset-select').value; const data = await api('/api/assets'); state.assets = data.assets || []; renderAssetSelect(); if([...$('#asset-select').options].some(option => option.value === previous)) $('#asset-select').value = previous; renderAssets(); updateComposer();}

async function loadMemories() {
  const [data,stats] = await Promise.all([api('/api/memories'),api('/api/learning')]); state.memories = data.memories || [];
  renderStats(stats); $('#preference-total').textContent = `${state.memories.length} ${state.memories.length === 1 ? 'preference' : 'preferences'}`;
  $('#memories-list').replaceChildren(...(state.memories.length ? state.memories.map(memory => {
    const remove = el('button',{type:'button',class:'icon-button','aria-label':'Delete this preference',title:'Delete preference'},icon('trash'));
    remove.addEventListener('click',async () => {remove.disabled = true;try{await api(`/api/memories/${encodeURIComponent(memory.id)}`,{method:'DELETE'});await loadMemories();toast('Preference deleted.');}catch(error){toast(error.message,true);remove.disabled = false;}});
    return el('article',{class:'memory-item'},icon('brain'),el('div',{},el('p',{},memory.text),el('small',{},`${memory.source === 'user' ? 'Saved by you' : 'Learned from feedback'} · ${dateLabel(memory.created_at)}`)),remove);
  }) : [empty('A fresh start.','Save a preference above, or choose what to remember when you give feedback.','brain')]));
}
async function loadSettings() { const data = await api('/api/settings'); $('#setting-text-model').value = data.text_model || 'qwen3:8b'; $('#setting-image-path').value = data.image_model_path || ''; $('#setting-video-path').value = data.video_model_path || ''; $('#setting-voice-path').value = data.voice_model_path || ''; $('#setting-device').value = data.device || 'auto'; $('#setting-ollama-url').textContent = data.ollama_url || 'http://127.0.0.1:11434'; }

function jobOptions() {
  const kind = state.kind, asset = selectedAsset();
  const value = id => Number($(id).value);
  if(kind === 'image') return {width:value('#image-width'),height:value('#image-height')};
  if(kind === 'animation') {const options = {effect:$('#overlay-effect').value,duration:value('#overlay-duration'),fps:value('#overlay-fps'),width:value('#overlay-width'),height:value('#overlay-height')};if($('#overlay-chroma-enabled').checked)options.chroma_key = $('#overlay-chroma').value;return options;}
  if(kind === 'voice') return asset ? {pitch_semitones:value('#voice-pitch'),speed:value('#voice-speed'),denoise:$('#voice-denoise').checked,normalize:$('#voice-normalize').checked} : {};
  if(kind === 'audio' || (kind === 'edit' && asset?.kind === 'audio')) return {noise_reduction:value('#audio-noise'),normalize:$('#audio-normalize').checked,start:value('#audio-start'),duration:value('#audio-duration')};
  if(kind === 'video' || (kind === 'edit' && asset?.kind === 'video')) { const options = {duration:value('#video-duration'),width:value('#video-width'),height:value('#video-height')}; if(asset?.kind === 'video') Object.assign(options,{start:value('#video-start'),denoise_audio:$('#denoise-audio').checked,muted:$('#mute-video').checked}); return options; }
  if(kind === 'edit') {
    const operation = $('#edit-operation').value;
    const options = {operation};
    if(['resize','crop'].includes(operation)) Object.assign(options,{width:value('#edit-width'),height:value('#edit-height')});
    if(operation === 'crop' && asset) { const width = Math.min(asset.width,value('#edit-width')),height = Math.min(asset.height,value('#edit-height')); const left = Math.floor((asset.width-width)/2),top = Math.floor((asset.height-height)/2); options.crop = {left,top,right:left+width,bottom:top+height}; }
    if(operation === 'rotate') options.angle = value('#edit-angle');
    if(['brightness','contrast','sharpen'].includes(operation)) options.factor = value('#edit-factor');
    return options;
  }
  return {};
}

decorateIcons();
$$('[data-view]').forEach(node => node.addEventListener('click',() => navigate(node.dataset.view)));
$$('[data-go]').forEach(node => node.addEventListener('click',() => navigate(node.dataset.go)));
$$('.composer-tab').forEach(node => {node.addEventListener('click',() => setKind(node.dataset.kind));node.addEventListener('keydown',event => { if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;event.preventDefault(); const tabs = $$('.composer-tab');let index = tabs.indexOf(node);index = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (index + (event.key === 'ArrowRight' ? 1 : -1)+tabs.length)%tabs.length;setKind(tabs[index].dataset.kind);tabs[index].focus();});});
$('#mobile-menu').addEventListener('click',() => $('.sidebar').classList.toggle('open'));
$('#asset-select').addEventListener('change',() => {const asset = selectedAsset(); if(asset?.duration){$('#audio-duration').value = Math.min(30,asset.duration);$('#audio-start').value = 0;$('#video-start').value = 0;} updateComposer();});
$('#edit-operation').addEventListener('change',updateComposer);
$('#overlay-chroma-enabled').addEventListener('change',() => {$('#overlay-chroma-control').hidden = !$('#overlay-chroma-enabled').checked;});
$$('[data-example]').forEach(node => node.addEventListener('click',() => { const example = node.dataset.example; setKind(example === 'brief' ? 'task' : example); $('#prompt').value = example === 'brief' ? 'Create a practical plan for a short cinematic video about finding beauty in everyday life. Include a shot list and a simple production schedule.' : example === 'edit' ? 'Create a black and white version of my photo.' : 'Animate this image with a gentle cinematic zoom.'; if(example === 'edit'){$('#edit-operation').value = 'grayscale';updateComposer();}$('#prompt').focus(); }));
$('#job-form').addEventListener('submit',async event => {
  event.preventDefault(); if(state.busy) return; inlineError('#composer-error');
  const asset = selectedAsset();
  if(['edit','audio','animation'].includes(state.kind) && !asset){inlineError('#composer-error','Choose a source file or upload one first.');return;}
  if(state.kind === 'animation' && Number($('#overlay-duration').value)*Number($('#overlay-fps').value)>240){inlineError('#composer-error','Keep overlay duration × frames per second at 240 frames or fewer.');return;}
  const defaults = {edit:'Edit uploaded media',audio:'Clean up background noise in uploaded sound',video:'Animate uploaded image or edit video',voice:asset ? 'Change the pitch and speed of this voice recording' : '',animation:'Create a transparent animated overlay for OBS'};
  const prompt = $('#prompt').value.trim() || defaults[state.kind] || '';
  if(!prompt){inlineError('#composer-error','Describe what you would like to make.');return;}
  state.busy = true; const button = $('#submit-job'); button.disabled = true;
  try {
    const job = await api('/api/jobs',{method:'POST',body:{prompt,kind:state.kind,asset_id:asset?.id || null,options:jobOptions(),use_memory:$('#use-memory').checked}});
    state.jobs.unshift(job); renderJobs(); $('#prompt').value = ''; toast('Job added. Your local agents will take it from here.');
  }catch(error){inlineError('#composer-error',error.message);}finally{state.busy = false;button.disabled = false;}
});
function startUpload() {if(!state.uploadBusy)$('#file-input').click();}
$('#composer-upload').addEventListener('click',startUpload); $('#library-upload').addEventListener('click',startUpload);
$('#file-input').addEventListener('change',async event => {
  const file = event.target.files?.[0]; if(!file)return;
  if(file.size > 64*1024*1024){toast('Choose a file smaller than 64 MB.',true);event.target.value = '';return;}
  state.uploadBusy = true; $('#composer-upload').disabled = true; $('#library-upload').disabled = true;
  const body = new FormData();body.append('file',file);toast('Adding your file to the local library…');
  try { const asset = await api('/api/assets',{method:'POST',body,timeout:90000}); await loadAssets(); if(state.view === 'studio'){ if(state.kind === 'task' || state.kind === 'game')setKind(asset.kind === 'audio' ? 'audio' : 'edit'); $('#asset-select').value = asset.id; updateComposer(); }toast('File added. It stays on this machine.'); }
  catch(error){toast(error.message,true);}finally{state.uploadBusy = false;$('#composer-upload').disabled = false;$('#library-upload').disabled = false;event.target.value = '';}
});
$('#memory-form').addEventListener('submit',async event => {event.preventDefault();inlineError('#memory-error');const button = $('button[type="submit"]',event.target);button.disabled = true;try{await api('/api/memories',{method:'POST',body:{text:$('#memory-text').value.trim()}});$('#memory-text').value = '';await loadMemories();toast('Preference saved locally.');}catch(error){inlineError('#memory-error',error.message);}finally{button.disabled = false;}});
$('#settings-form').addEventListener('submit',async event => {event.preventDefault();inlineError('#settings-error');const button = $('#save-settings');button.disabled = true;try{await api('/api/settings',{method:'POST',body:{text_model:$('#setting-text-model').value.trim(),image_model_path:$('#setting-image-path').value.trim(),video_model_path:$('#setting-video-path').value.trim(),voice_model_path:$('#setting-voice-path').value.trim(),device:$('#setting-device').value}});await loadStatus();toast('Local model settings saved.');}catch(error){inlineError('#settings-error',error.message);}finally{button.disabled = false;}});
$('#refresh-status').addEventListener('click',async event => {const button = event.currentTarget;button.disabled = true;try{await loadStatus();toast('Local model status refreshed.');}catch(error){toast(error.message,true);}finally{button.disabled = false;}});
window.addEventListener('hashchange',() => navigate(location.hash.slice(1)));
setKind('auto');navigate(location.hash.slice(1) || 'studio');
Promise.allSettled([loadStatus(),loadJobs(),loadAssets()]).then(results => {if(results.some(result => result.status === 'rejected'))toast('Some local app data could not load. Check that Loom is running.',true);});
let polling = false, quietTicks = 0;
setInterval(async () => {
  if(polling || document.hidden)return;
  const active = state.jobs.some(job => ['queued','running'].includes(job.status));
  if(!active && ++quietTicks < 8)return;quietTicks = 0;polling = true;
  const before = state.jobs.filter(job => job.status === 'completed').length;
  try {await loadJobs();if(state.jobs.filter(job => job.status === 'completed').length > before){await loadAssets();await loadStatus();}}
  catch(error){if(active)toast(error.message,true);}finally{polling = false;}
},2000);
