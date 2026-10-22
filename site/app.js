'use strict';
const $ = id => document.getElementById(id);
const state = {payload:null, horizon:'短期', side:'すべて', market:'すべて', signal:'候補', term:''};
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const isFiniteNumber = x => typeof x === 'number' && Number.isFinite(x);
const fmt = value => {
  if (!isFiniteNumber(value)) return '—';
  return new Intl.NumberFormat('ja-JP',{maximumFractionDigits: Math.abs(value)>=1000 ? 1 : Math.abs(value)>=1 ? 3 : 6}).format(value);
};
const displayTime = iso => {
  if(!iso)return '初回スキャン待ち';
  const d=new Date(iso);
  return Number.isNaN(d.getTime()) ? '時刻不明' : new Intl.DateTimeFormat('ja-JP',{timeZone:'Asia/Tokyo',year:'numeric',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}).format(d)+' JST';
};
const safeDaysOld = iso => iso ? Math.max(0,(Date.now()-new Date(iso).getTime())/86400000) : null;
const classify = s => s?.includes('買い') ? 'buy' : s?.includes('ショート') ? 'sell' : '';

function makeSpark(line, className) {
  const arr = line?.values?.filter(v => isFiniteNumber(v)) || [];
  if (arr.length < 3) return '';
  const lo = Math.min(...arr), hi = Math.max(...arr), span = hi - lo || 1;
  const pts=arr.map((n,i)=>`${(i*300/(arr.length-1)).toFixed(1)},${(48-44*(n-lo)/span).toFixed(1)}`).join(' ');
  const color=className==='buy'?'#57e0b0':className==='sell'?'#ff8d94':'#80aaca';
  return `<div class="sparkline" aria-label="過去60本以内の参考終値推移"><svg viewBox="0 0 300 52" preserveAspectRatio="none" role="img"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2.2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/></svg></div>`;
}
function card(r,charts){
  const status=String(r.signal||'様子見');
  const cls=classify(r.side);
  const tagClass=status.includes('初動')?cls:status.includes('準備')?'ready':'';
  const assetKey=`${r.market}::${r.name}`;
  const bits = [r.rsi!=null?`RSI ${fmt(r.rsi)}`:null,
    r.volume_ratio!=null?`株出来高 ${fmt(r.volume_ratio)}×`:null,
    r.rs20!=null?`RS20 ${fmt(r.rs20)}pt`:null,
    r.risk_atr!=null?`損切 ${fmt(r.risk_atr)} ATR`:null,
    r.bb_width_rank!=null?`BB順位 ${fmt(r.bb_width_rank)}%`:null].filter(Boolean);
  const bitHtml=bits.map(b=>`<span class="metric">${esc(b)}</span>`).join('');
  const tradingRisk=(isFiniteNumber(r.price)&&isFiniteNumber(r.stop)&&r.price>0)?(Math.abs(r.price-r.stop)/r.price*100):null;
  return `<article class="card ${cls}">
    <div class="head"><div><div class="labels"><span class="tag">${esc(r.market)}</span><span class="tag ${tagClass}">${esc(status)}</span></div>
    <h3 class="title">${esc(r.name)}</h3><div class="ticker">${esc(r.symbol)} &nbsp;·&nbsp; ${esc(r.horizon)}</div></div>
    <div class="score"><strong>${isFiniteNumber(r.score)?fmt(r.score):'—'}</strong><small>SIGNAL SCORE</small></div></div>
    <div class="price-row"><div><strong>${fmt(r.price)}</strong><small>参考終値（SBI約定価格ではありません）</small></div><span class="date">${esc(r.bar_date||'—')}</span></div>
    <div class="risk"><div class="risk-item stop"><small>損切り参考</small><b>${fmt(r.stop)}</b></div><div class="risk-item profit"><small>目標価格 2R</small><b>${fmt(r.target_2r)}</b></div></div>
    <div class="indicators">${bitHtml}</div>
    ${makeSpark(charts[assetKey],cls)}
    <div class="details">
      <div class="details-line"><span>サイクル</span><b>${esc(r.cycle||'判定不足')}</b></div>
      <div class="details-line"><span>週足方向</span><b>${esc(r.weekly_trend||'—')}</b></div>
      <div class="details-line"><span>参考損切り幅</span><b>${tradingRisk!=null?fmt(tradingRisk)+'%':'—'}</b></div>
      <div class="details-line"><span>満たした条件</span><b>${esc(r.passed_checks||'—')}</b></div>
    </div><p class="note">${esc(r.note||'公開参考市場データを使用')}</p></article>`;
}
function filterRows(){
  const p=state.payload;
  if(!p)return [];
  const term=state.term.toLocaleLowerCase('ja-JP').trim();
  const scoreSignal=s=>s?.includes('初動')?0:s?.includes('準備')?1:s?.includes('要確認')?2:3;
  return (p.rows||[]).filter(r=>
    r.horizon===state.horizon &&
    (state.side==='すべて'||r.side===state.side) &&
    (state.market==='すべて'||r.market===state.market) &&
    (state.signal==='すべて'||(state.signal==='候補' && (r.signal?.includes('初動')||r.signal?.includes('準備')))||(state.signal==='初動'&&r.signal?.includes('初動'))||(state.signal==='準備'&&r.signal?.includes('準備'))) &&
    (!term||String(r.name+' '+r.symbol+' '+r.market).toLocaleLowerCase('ja-JP').includes(term))
  ).sort((a,b)=>(scoreSignal(a.signal)-scoreSignal(b.signal)) || ((b.score||0)-(a.score||0)));
}
function banner(message, type='info') { $('message').innerHTML=message?`<div class="banner ${type==='info'?'':esc(type)}">${esc(message)}</div>`:''; }
function render(){
  const p=state.payload;
  if(!p)return;
  const rows=(p.rows||[]).filter(r=>r.horizon===state.horizon);
  const count=predicate=>rows.filter(predicate).length;
  $('n-buy').textContent=count(r=>r.signal==='買い初動');
  $('n-short').textContent=count(r=>r.signal==='ショート初動');
  $('n-ready').textContent=count(r=>r.signal==='買い準備'||r.signal==='ショート準備');
  $('n-rows').textContent=rows.length;
  $('updated-at').textContent=displayTime(p.meta?.generated_at);
  $('feed-count').textContent=`${p.meta?.assets_analyzed ?? 0} / ${p.meta?.assets_enabled ?? 0}`;
  document.querySelectorAll('.horizon').forEach(el=>{const active=el.dataset.horizon===state.horizon;el.classList.toggle('active',active);el.setAttribute('aria-pressed',String(active));});
  document.querySelectorAll('.chip').forEach(el=>{const active=el.dataset.side===state.side;el.classList.toggle('active',active);el.setAttribute('aria-pressed',String(active));});
  const filtered=filterRows();
  $('filtered-count').textContent=filtered.length+'件';
  $('results').innerHTML=filtered.length?filtered.slice(0,400).map(r=>card(r,p.charts||{})).join(''):`<div class="empty"><b>該当する銘柄はありません</b><p>${p.meta?.generated_at?'絞り込み条件を変更するか、次回の更新を確認してください。':'初回の分析実行前です。GitHub Actions でスキャンを実行してください。'}</p></div>`;
  const age=safeDaysOld(p.meta?.generated_at);
  const feeds=p.meta?.assets_analyzed||0;
  if(!p.meta?.generated_at){
    $('health-dot').className='status-pip warn';$('health-text').textContent='未実行';
    banner('初回のスキャンがまだ完了していません。GitHub の Actions で「Mobile scanner - analyze and publish」を実行してください。','warn');
  }else if(age>2){
    $('health-dot').className='status-pip bad';$('health-text').textContent='更新遅延';
    banner(`前回の分析から${Math.floor(age)}日以上経過しています。相場判断には使用せず、GitHub Actions を確認してください。`,'error');
  }else if(feeds===0){
    $('health-dot').className='status-pip bad';$('health-text').textContent='取得失敗';
    banner('価格データを取得できませんでした。参考シグナルは表示できません。GitHub Actionsのログを確認してください。','error');
  }else if((p.meta?.issue_count||0)>0){
    $('health-dot').className='status-pip ok';$('health-text').textContent='一部欠損';
    banner(`取得 ${feeds}/${p.meta?.assets_enabled} 商品。未対応・取得不足・解析対象外の銘柄が${p.meta.issue_count}件あります。対象すべての分析を保証するものではありません。`,'info');
  }else{
    $('health-dot').className='status-pip ok';$('health-text').textContent='更新済';banner('');
  }
}
async function reload(){
  $('refresh').disabled=true;
  $('health-text').textContent='読込中';
  try{
    const res=await fetch('./data/latest.json?ts='+Date.now(),{cache:'no-store'});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const json=await res.json();
    if(!json.meta||!Array.isArray(json.rows))throw new Error('不正なレポート形式');
    state.payload=json;render();
  }catch(err){
    $('health-dot').className='status-pip bad';$('health-text').textContent='読込失敗';
    banner('レポートを読み込めませんでした。ネットワーク接続とGitHub Pages公開設定を確認してください（'+String(err.message).slice(0,80)+'）。','error');
    $('results').innerHTML='<div class="empty"><b>公開済みのデータを取得できません</b><p>ブラウザを再読込してください。</p></div>';
  }finally{ $('refresh').disabled=false; }
}
document.querySelectorAll('.horizon').forEach(el=>el.addEventListener('click',()=>{state.horizon=el.dataset.horizon;render();}));
document.querySelectorAll('.chip').forEach(el=>el.addEventListener('click',()=>{state.side=el.dataset.side;render();}));
$('market').addEventListener('change',e=>{state.market=e.target.value;render();});
$('signal').addEventListener('change',e=>{state.signal=e.target.value;render();});
$('search').addEventListener('input',e=>{state.term=e.target.value;render();});
$('refresh').addEventListener('click',reload);
reload();
