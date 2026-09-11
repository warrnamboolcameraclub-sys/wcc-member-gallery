const state = {
  photos: [],
  ioty: [],
  visible: [],
  visibleLimit: 12,
  lightboxIndex: 0,
  mode: 'members'
};

const embeddedMode = new URLSearchParams(location.search).get('embed') === '1';

function pageSize(){
  return 50;
}

state.visibleLimit = pageSize();

if(embeddedMode){
  document.body.classList.add('embed-mode');
}

const $ = id => document.getElementById(id);
const gallery = $('gallery');
const iotyGallery = $('iotyGallery');
const memberSelect = $('memberSelect');
const yearSelect = $('yearSelect');
const monthSelect = $('monthSelect');
const subjectSelect = $('subjectSelect');
const resultSelect = $('resultSelect');

function esc(value=''){
  return String(value).replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  })[c]);
}

function displayTitle(value=''){
  let title = String(value).trim();

  // WCC titles can arrive in several forms after MyPhotoClub processing, e.g.
  // S_003_Title, O_003_Title, S 003 Title, O 003 Title, 003_Title, or 003 Title.
  // Strip only a leading competition/member prefix; never remove digits elsewhere.
  title = title.replace(/^(?:[SO][\s_-]*)?\d{3}(?:[\s_-]+|$)/i, '');

  // Convert filename-style underscores to normal spaces for display.
  title = title.replace(/_+/g, ' ');

  return title.replace(/\s+/g, ' ').trim();
}

function isAward(result=''){
  return result.trim().toLowerCase() !== 'accepted';
}

function niceDate(value){
  if(!value) return '';
  const d = new Date(value + (value.length === 10 ? 'T00:00:00' : ''));
  if(Number.isNaN(d.getTime())) return value;
  return new Intl.DateTimeFormat('en-AU',{month:'short',year:'numeric'}).format(d);
}

const monthOrder = ['January','February','March','April','May','June','July','August','September','October','November','December'];

function competitionLabel(photo){
  const bits = [];
  if(photo.competitionMonth) bits.push(photo.competitionMonth);
  if(photo.competitionYear) bits.push(photo.competitionYear);
  return bits.join(' ') || photo.competition;
}

function subjectFor(photo){
  return photo.setSubject || '';
}

function card(photo, index, target='members'){
  const award = isAward(photo.result);
  return `<article class="card">
    <div class="imgbox" data-index="${index}" data-target="${target}" tabindex="0" role="button" aria-label="Enlarge ${esc(displayTitle(photo.title))}">
      <img src="${esc(photo.image)}" alt="${esc(displayTitle(photo.title))} by ${esc(photo.member)}" loading="lazy">
      <span class="zoom-hint">Click to enlarge</span>
    </div>
    <div class="card-body">
      <h3 class="card-title">${esc(displayTitle(photo.title))}</h3>
      <div class="member">${esc(photo.member)}</div>
      <div class="meta">${esc(competitionLabel(photo))}${subjectFor(photo) ? ` · Set subject: ${esc(subjectFor(photo))}` : ''}<br>${esc(photo.section)}</div>
      <span class="result ${award ? 'award' : ''}">${esc(photo.result)}</span>
    </div>
  </article>`;
}

function populateFilters(){
  const params = new URLSearchParams(location.hash.replace(/^#/,''));

  memberSelect.dataset.pending = params.get('member') || '';
  yearSelect.dataset.pending = params.get('year') || '';
  monthSelect.dataset.pending = params.get('month') || '';
  subjectSelect.dataset.pending = params.get('subject') || '';

  refreshFacetOptions(true);
}


function currentFilters(){
  return {
    member: memberSelect.value || memberSelect.dataset.pending || '',
    year: yearSelect.value || yearSelect.dataset.pending || '',
    month: monthSelect.value || monthSelect.dataset.pending || '',
    subject: subjectSelect.value || subjectSelect.dataset.pending || '',
    result: resultSelect.value || ''
  };
}

function matchesFilters(photo, filters, ignore=''){
  if(ignore !== 'member' && filters.member && photo.member !== filters.member) return false;
  if(ignore !== 'year' && filters.year && String(photo.competitionYear) !== String(filters.year)) return false;
  if(ignore !== 'month' && filters.month && photo.competitionMonth !== filters.month) return false;
  if(ignore !== 'subject' && filters.subject && subjectFor(photo) !== filters.subject) return false;

  if(ignore !== 'result' && filters.result){
    if(filters.result === 'award' && !isAward(photo.result)) return false;
    if(filters.result === 'Accepted' && photo.result !== 'Accepted') return false;
  }
  return true;
}

function setSelectOptions(select, values, allLabel, currentValue, formatter=v=>v){
  const options = [`<option value="">${allLabel}</option>`]
    .concat(values.map(v=>`<option value="${esc(v)}">${esc(formatter(v))}</option>`));
  select.innerHTML = options.join('');

  if(currentValue && values.map(String).includes(String(currentValue))){
    select.value = String(currentValue);
  } else {
    select.value = '';
  }
  delete select.dataset.pending;
}

function availableValues(ignore, getter, sorter){
  const filters = currentFilters();
  const values = [...new Set(
    state.photos
      .filter(p=>matchesFilters(p, filters, ignore))
      .map(getter)
      .filter(v=>v !== null && v !== undefined && v !== '')
  )];
  return sorter ? values.sort(sorter) : values.sort((a,b)=>String(a).localeCompare(String(b)));
}

function refreshFacetOptions(initial=false){
  const before = currentFilters();

  const members = availableValues('member', p=>p.member, (a,b)=>a.localeCompare(b));
  const years = availableValues('year', p=>p.competitionYear, (a,b)=>b-a);
  const months = availableValues('month', p=>p.competitionMonth,
    (a,b)=>monthOrder.indexOf(a)-monthOrder.indexOf(b));
  const subjects = availableValues('subject', p=>subjectFor(p), (a,b)=>a.localeCompare(b));

  setSelectOptions(memberSelect, members, 'All members', before.member);
  setSelectOptions(yearSelect, years, 'All years', before.year);
  setSelectOptions(monthSelect, months, 'All months', before.month);
  setSelectOptions(subjectSelect, subjects, 'All set subjects', before.subject);

  if(!initial){
    // Re-evaluate once in case one selection became invalid after another facet changed.
    const after = currentFilters();
    if(JSON.stringify(before) !== JSON.stringify(after)){
      refreshFacetOptions(true);
    }
  }
}

function facetChanged(){
  state.visibleLimit = pageSize();
  refreshFacetOptions();
  renderMembers();
}

function updateHash(){
  const params = new URLSearchParams();
  if(memberSelect.value) params.set('member',memberSelect.value);
  if(yearSelect.value) params.set('year',yearSelect.value);
  if(monthSelect.value) params.set('month',monthSelect.value);
  if(subjectSelect.value) params.set('subject',subjectSelect.value);
  history.replaceState(null,'',params.toString() ? `#${params}` : location.pathname + location.search);
}

function renderMembers(){
  const filters = currentFilters();
  let shown = state.photos.filter(p=>matchesFilters(p, filters));

  shown.sort((a,b)=>{
    const year = (b.competitionYear||0) - (a.competitionYear||0);
    if(year) return year;
    const month = monthOrder.indexOf(b.competitionMonth) - monthOrder.indexOf(a.competitionMonth);
    if(month) return month;
    return String(a.title||'').localeCompare(String(b.title||''));
  });

  state.visible = shown;
  $('galleryTitle').textContent = memberSelect.value || 'All members';
  const memberCount = new Set(shown.map(p=>p.member)).size;
  const active = [];
  if(yearSelect.value) active.push(yearSelect.value);
  if(monthSelect.value) active.push(monthSelect.value);
  if(subjectSelect.value) active.push(`Set subject: ${subjectSelect.value}`);
  $('gallerySummary').textContent =
    `${shown.length.toLocaleString()} image${shown.length===1?'':'s'}` +
    (!memberSelect.value ? ` from ${memberCount} photographer${memberCount===1?'':'s'}` : '') +
    (active.length ? ` · ${active.join(' · ')}` : '');

  const displayCount = Math.min(state.visibleLimit, shown.length);
  gallery.innerHTML = shown.slice(0, displayCount).map((p,i)=>card(p,i,'members')).join('');

  const moreRemaining = shown.length - displayCount;
  const hasMore = moreRemaining > 0;
  $('loadMoreWrap').hidden = !hasMore;
  $('loadMore').hidden = !hasMore;
  $('loadMoreStatus').textContent =
    hasMore ? `Showing ${displayCount.toLocaleString()} of ${shown.length.toLocaleString()} images` : '';
  if(hasMore){
    $('loadMore').textContent = `Load more (${Math.min(pageSize(), moreRemaining)})`;
  }

  $('emptyState').hidden = shown.length !== 0;
  updateHash();
}

function renderIoty(){
  const shown = state.ioty
    .map((photo,index)=>({photo,index}))
    .sort((a,b)=>{
      const section = String(a.photo.section||'').localeCompare(String(b.photo.section||''));
      if(section) return section;
      const rank = {'1st Place':1,'2nd Place':2,'3rd Place':3};
      return (rank[a.photo.result]||99)-(rank[b.photo.result]||99);
    });

  // Preserve each photograph's original index from state.ioty.
  // The lightbox reads state.ioty[data-index], so using the sorted
  // display position would open the wrong photograph.
  iotyGallery.innerHTML = shown
    .map(({photo,index})=>card(photo,index,'ioty'))
    .join('');
}

function switchTab(mode){
  state.mode = mode;
  const members = mode==='members';
  $('membersSection').hidden = !members;
  $('iotySection').hidden = members;
  $('membersTab').classList.toggle('active',members);
  $('iotyTab').classList.toggle('active',!members);
}

function openLightbox(index,target,anchor=null){
  const list = target==='ioty' ? state.ioty : state.visible;
  if(!list.length) return;
  state.mode = target;
  state.lightboxIndex = (Number(index)+list.length)%list.length;
  const p = list[state.lightboxIndex];
  $('lightboxImage').src = p.largeImage || p.image.replace('-small.','-large.');
  $('lightboxImage').alt = `${displayTitle(p.title)} by ${p.member}`;
  $('lightboxTitle').textContent = displayTitle(p.title);
  $('lightboxMeta').textContent = `${p.member} · ${p.competition} · ${p.section} · ${p.result}`;
  if(embeddedMode && anchor){
    const rect = anchor.getBoundingClientRect();
    const top = Math.max(0, rect.top + window.scrollY - 8);
    $('lightbox').style.top = `${top}px`;
  }
  $('lightbox').classList.add('open');
  $('lightbox').setAttribute('aria-hidden','false');
  if(!embeddedMode){
    document.body.style.overflow='hidden';
  }
}

function moveLightbox(delta){
  const list = state.mode==='ioty' ? state.ioty : state.visible;
  openLightbox(state.lightboxIndex+delta,state.mode);
}

function closeLightbox(){
  $('lightbox').classList.remove('open');
  $('lightbox').setAttribute('aria-hidden','true');
  $('lightboxImage').src='';
  $('lightbox').style.top = '';
  document.body.style.overflow='';
}

function galleryActivate(e){
  const box = e.target.closest('.imgbox');
  if(!box) return;
  if(e.type==='keydown' && !['Enter',' '].includes(e.key)) return;
  if(e.type==='keydown') e.preventDefault();
  openLightbox(box.dataset.index,box.dataset.target,box);
}

async function init(){
  try{
    const [photosRes,iotyRes] = await Promise.all([
      fetch('data/photos.json',{cache:'no-store'}),
      fetch('data/ioty.json',{cache:'no-store'})
    ]);
    if(!photosRes.ok || !iotyRes.ok) throw new Error('Gallery data could not be loaded.');
    state.photos = await photosRes.json();
    state.ioty = await iotyRes.json();
    $('totalImages').textContent = state.photos.length.toLocaleString();
    populateFilters();
    renderMembers();
    renderIoty();
  }catch(err){
    gallery.innerHTML = `<div class="empty">Unable to load gallery data. ${esc(err.message)}</div>`;
    console.error(err);
  }
}

memberSelect.addEventListener('change',facetChanged);
yearSelect.addEventListener('change',facetChanged);
monthSelect.addEventListener('change',facetChanged);
subjectSelect.addEventListener('change',facetChanged);
resultSelect.addEventListener('change',facetChanged);
$('clearFilters').addEventListener('click',()=>{
  memberSelect.value=''; yearSelect.value=''; monthSelect.value=''; subjectSelect.value=''; resultSelect.value='';
  state.visibleLimit = pageSize();
  refreshFacetOptions();
  renderMembers();
});

$('loadMore').addEventListener('click',()=>{
  state.visibleLimit += pageSize();
  renderMembers();
});
$('membersTab').addEventListener('click',()=>switchTab('members'));
$('iotyTab').addEventListener('click',()=>switchTab('ioty'));
gallery.addEventListener('click',galleryActivate);
gallery.addEventListener('keydown',galleryActivate);
iotyGallery.addEventListener('click',galleryActivate);
iotyGallery.addEventListener('keydown',galleryActivate);
$('lightboxClose').addEventListener('click',closeLightbox);
$('lightboxPrev').addEventListener('click',()=>moveLightbox(-1));
$('lightboxNext').addEventListener('click',()=>moveLightbox(1));
$('lightbox').addEventListener('click',e=>{if(e.target===$('lightbox')) closeLightbox()});
document.addEventListener('keydown',e=>{
  if(!$('lightbox').classList.contains('open')) return;
  if(e.key==='Escape') closeLightbox();
  if(e.key==='ArrowLeft') moveLightbox(-1);
  if(e.key==='ArrowRight') moveLightbox(1);
});
init();
