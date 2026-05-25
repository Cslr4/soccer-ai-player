const API = window.location.origin;
let pid = null;
let state = null;
let pendingOffers = [];
const HARD_ATTRS = ['射门','跑位','定位球','传球','盘带','技术','才华','盯人','抢断','站位','强壮','速度','跳跃','体力','头球'];
const SOFT_ATTRS = ['意志力','勇敢','抗压能力','稳定性','情绪控制','职业态度','团队精神','人际处理','公众口碑','声望','伤病抗性','多面性','双足均衡'];
let messages = [];
let currentEvent = null;

const $ = s => document.querySelector(s);
function render(h) { $('#app').innerHTML = h; }
function scrollDown() {
  const m = $('#main-area');
  if (m) setTimeout(() => m.scrollTop = m.scrollHeight, 80);
}

async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  if (!r.ok) { const e = await r.json().catch(()=>({detail:r.statusText})); throw new Error(e.detail); }
  return r.json();
}

// 流式 SSE 请求 —— 返回 Promise，onChunk 逐 token 回调
function apiStream(path, body, onChunk) {
  return new Promise(async (resolve, reject) => {
    try {
      const r = await fetch(API + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({ detail: r.statusText }));
        reject(new Error(e.detail)); return;
      }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === 'chunk') onChunk(evt.content);
            else if (evt.type === 'done') { resolve(evt); return; }
            else if (evt.type === 'error') { reject(new Error(evt.message)); return; }
          }
        }
      }
      reject(new Error('流意外结束'));
    } catch (e) { reject(e); }
  });
}

// ======================== 消息系统 ========================
function addSys(s) { messages.push(`<div class="msg system">${s}</div>`); }
function addAI(s) { messages.push(`<div class="msg ai">${s}</div>`); }
function addPlayer(s) { messages.push(`<div class="msg player">${s}</div>`); }
function addNews(s) { messages.push(`<div class="msg news">📰 ${s}</div>`); }
function addIntro(s) { messages.push(`<div class="msg intro">${s}</div>`); }
function addEventCard(evt) {
  currentEvent = evt;
  const opts = (evt.options || []).map(o => `
    <button class="opt-btn" onclick="chooseOpt('${o.id}')">
      <span class="oid">${o.id}</span>${o.text}
    </button>`).join('');
  messages.push(`
    <div class="event-card" id="evt-card">
      <div class="cat">${evt.category}</div>
      <div class="tit">${evt.title}</div>
      <div class="desc">${evt.description}</div>
      <div class="opts">
        ${opts}
        <button class="opt-btn custom" onclick="showCustomInput()">
          <span class="oid">?</span>自定义行动...
        </button>
      </div>
    </div>`);
}

function showCustomInput() {
  const card = document.getElementById('evt-card');
  if (!card) return;
  const optsDiv = card.querySelector('.opts');
  if (!optsDiv) return;
  optsDiv.innerHTML = `
    <textarea id="custom-input" style="width:100%;padding:10px 14px;background:var(--bg2);color:var(--text3);
      border:1px solid var(--gold);border-radius:var(--radius2);font-size:15px;font-family:var(--font);
      outline:none;resize:vertical;min-height:70px;" placeholder="输入你的自定义行动..."></textarea>
    <div style="display:flex;gap:8px;margin-top:8px;">
      <button class="opt-btn" onclick="doCustom()" style="flex:1;border-color:var(--gold);color:var(--gold);">✓ 确定</button>
      <button class="opt-btn" onclick="cancelCustom()" style="flex:1;border-color:var(--text2);color:var(--text2);">✕ 取消</button>
    </div>`;
  setTimeout(() => document.getElementById('custom-input')?.focus(), 100);
}

function cancelCustom() {
  const card = document.getElementById('evt-card');
  if (!card) return;
  const optsDiv = card.querySelector('.opts');
  if (!optsDiv || !currentEvent) return;
  const evt = currentEvent;
  const optsHtml = (evt.options || []).map(o => `
    <button class="opt-btn" onclick="chooseOpt('${o.id}')">
      <span class="oid">${o.id}</span>${o.text}
    </button>`).join('');
  optsDiv.innerHTML = optsHtml + `<button class="opt-btn custom" onclick="showCustomInput()"><span class="oid">?</span>自定义行动...</button>`;
}

async function doCustom() {
  const t = document.getElementById('custom-input')?.value?.trim();
  if (!t) return;
  disableEventBtns();
  messages = messages.filter(m => !m.includes('evt-card'));
  addPlayer(`【自定义】${t}`);
  const phId = 's-' + Date.now();
  messages.push(`<div class="msg ai" id="${phId}"></div>`);
  renderGame();
  try {
    const result = await apiStream(
      `/api/game/${pid}/event_choice/stream`,
      { option_id: 'custom', custom_text: t },
      (chunk) => { const el = document.getElementById(phId); if (el) { el.textContent += chunk; scrollDown(); } }
    );
    const idx = messages.findIndex(m => m.includes(phId));
    if (idx >= 0) messages[idx] = `<div class="msg ai">${result.narrative}</div>`;
    state = await api('GET', `/api/game/${pid}/state`);
    currentEvent = null;
    handleNewAchievements(result.new_achievements);
    showAfterEvent(result.events_done, result.events_total);
    renderGame();
  } catch (e) {
    messages = messages.filter(m => !m.includes(phId));
    addSys('❌ ' + e.message); renderGame();
  }
}
function addSettle(data) {
  let chgHtml = '';
  // 合并事件变化 + 赛季成长
  const ch = data.attr_changes || {};
  const gr = data.growth_changes || {};
  const allKeys = new Set([...Object.keys(ch), ...Object.keys(gr)]);
  const merged = {};
  allKeys.forEach(k => { merged[k] = (ch[k] || 0) + (gr[k] || 0); });
  const keys = Object.keys(merged).filter(k => merged[k] !== 0 || k.includes('溢出'));
  if (keys.length > 0) {
    chgHtml = keys.map(k => {
      const v = merged[k];
      const isOverflow = k.includes('→');
      const cls = isOverflow ? '' : (v > 0 ? 'pos' : 'neg');
      const sign = v > 0 ? '+' : '';
      return `<div class="change-item ${cls}" style="${isOverflow ? 'color:var(--text2);border-left-color:var(--text2);' : ''}">${isOverflow ? '↪ ' + k : k + ' ' + sign + v}</div>`;
    }).join('');
  } else { chgHtml = '<div class="change-item">无变化</div>'; }

  // 结算面板只显4条，其余进新闻栏
  const allNews = data.world_news || [];
  const showNews = allNews.slice(0, 4);
  const newsHtml = showNews.map(n => `<div class="msg news">📰 ${n}</div>`).join('')
    + (allNews.length > 4 ? `<div style="text-align:center;font-size:12px;color:var(--text2);margin-top:4px;">共 ${allNews.length} 条新闻，点击 📰 新闻 查看全部</div>` : '');

  messages.push(`
    <div class="settle-panel">
      <div class="s-title">📋 回合结算</div>
      <div class="s-section"><h3>📖 剧情推进</h3><div class="s-text">${data.narrative}</div></div>
      <div class="s-section"><h3>🌍 足坛大事</h3>${newsHtml || '<div style="color:var(--text2)">暂无</div>'}</div>
      <div class="s-section"><h3>📊 属性变动</h3><div class="settle-changes">${chgHtml}</div></div>
      <div class="s-section" style="text-align:center;">${data.buff ? `<div style="display:inline-block;padding:6px 16px;background:rgba(230,184,67,0.1);border:1px solid var(--gold);border-radius:20px;font-size:13px;color:var(--gold);margin-bottom:8px;">⚡ ${data.buff}</div>` : ''}</div>
      <div class="s-section" style="text-align:center;">
        <div style="color:var(--text2)">球队 #${data.team_rank} | ${data.team_points}分 | 氛围：${data.atmosphere || ''} | ${data.temp_status}</div>
        <div style="color:var(--green);margin-top:6px;">第${data.season}赛季 · ${data.next_round}</div>
      </div>
      <div style="text-align:center;margin-top:14px;">
        <button class="action-btn btn-primary" onclick="doRoundStart()">进入下一回合 →</button>
      </div>
    </div>`);
}

function renderMsgs() { return messages.join(''); }

// ======================== 模态面板 ========================
let activeModal = null;
function openModal(id) {
  closeModal();
  const ov = document.createElement('div');
  ov.className = 'modal-overlay';
  ov.id = 'modal-overlay';
  ov.onclick = e => { if (e.target === ov) closeModal(); };
  document.body.appendChild(ov);
  activeModal = id;
  fillModal(id, ov);
}
function closeModal() {
  const el = document.getElementById('modal-overlay');
  if (el) el.remove();
  activeModal = null;
}
function fillModal(id, ov) {
  if (!state) return;
  const { player: p, season: s } = state;
  if (id === 'attrs') {
    // 分组：得分 / 传控 / 防守 / 身体 / 精神 / 社交 / 特质
    const row = (a, cls) => `<div class="attr-row"><span class="attr-name">${a}</span><div class="attr-bar-wrap"><div class="attr-bar ${cls}" style="width:${p.attrs[a]}%"></div></div><span class="attr-val">${p.attrs[a]}</span></div>`;
    const section = (title, attrs, cls) => `<div class="attr-sect"><h3>${title}</h3>${attrs.map(a => row(a, cls)).join('')}</div>`;

    const hSum = HARD_ATTRS.reduce((t,a) => t + (p.attrs[a]||0), 0);
    const sSum = SOFT_ATTRS.reduce((t,a) => t + (p.attrs[a]||0), 0);

    const cols = `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 20px;">
        <div>
          ${section('🎯 进攻', ['射门','跑位','定位球'], 'hard')}
          ${section('🎨 传控', ['传球','盘带','技术','才华'], 'hard')}
          ${section('🛡 防守', ['盯人','抢断','站位'], 'hard')}
          ${section('💪 身体', ['强壮','速度','跳跃','体力','头球'], 'hard')}
        </div>
        <div>
          ${section('🧠 精神', ['意志力','勇敢','抗压能力','稳定性','情绪控制'], 'soft')}
          ${section('🤝 社交', ['职业态度','团队精神','人际处理','公众口碑','声望'], 'soft')}
          ${section('🔬 特质', ['伤病抗性','多面性','双足均衡'], 'soft')}
        </div>
      </div>`;

    ov.innerHTML = `<div class="modal-panel" style="max-width:700px;">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2>${p.name} · 个人属性</h2>
      ${cols}
      <div style="display:flex;justify-content:center;gap:40px;margin-top:10px;padding-top:10px;border-top:1px solid var(--border2);font-size:13px;color:var(--text2);">
        <span>硬实力总和：<b style="color:var(--green3)">${hSum}</b></span>
        <span>软实力总和：<b style="color:var(--green3)">${sSum}</b></span>
      </div>
      <div style="text-align:center;font-size:13px;color:var(--text2);margin-top:8px;">${p.age}岁 | ${p.height}cm | ${p.weight}kg | ${p.position} | 世界${p.team_tier} | 联赛${p.league_level || '中游'} | ${p.temp_status}</div>
    </div>`;
  } else if (id === 'team') {
    ov.innerHTML = `<div class="modal-panel">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2>${p.team_name}</h2>
      <div class="team-grid">
        <div class="team-stat"><div class="l">联赛排名</div><div class="v">#${s.team_rank}</div></div>
        <div class="team-stat"><div class="l">积分</div><div class="v">${s.team_points}</div></div>
        <div class="team-stat"><div class="l">已赛</div><div class="v">${s.team_games}</div></div>
        <div class="team-stat"><div class="l">世界等级</div><div class="v" style="font-size:15px;">${p.team_tier}</div></div>
        <div class="team-stat"><div class="l">联赛地位</div><div class="v" style="font-size:15px;">${p.league_level || '中游'}</div></div>
        <div class="team-stat"><div class="l">队内氛围</div><div class="v" style="font-size:18px;">${s.atmosphere || '平淡'}</div></div>
        <div class="team-stat"><div class="l">我的地位</div><div class="v" style="font-size:16px;color:var(--green3);">${p.locker_status || '普通成员'}</div></div>
      </div>
      <div style="margin-top:14px;padding:10px;background:var(--bg2);border-radius:var(--radius2);">
        <div style="font-size:13px;color:var(--text2);margin-bottom:4px;">📝 个人合同</div>
        <div style="font-size:15px;color:var(--text3);">周薪 <b style="color:var(--gold);">${Number(p.weekly_wage||5).toFixed(1)}</b> 万欧 · 剩 <b style="color:var(--green3);">${p.seasons_left || 3}</b> 赛季${(p.release_clause > 0) ? ' · 解约金 ' + Number(p.release_clause).toFixed(0) + '万' : ''}</div>
      </div>
      <div style="margin-top:14px;padding:10px;background:var(--bg2);border-radius:var(--radius2);text-align:center;">
        <span style="color:var(--text2)">当前</span>
        <span style="color:var(--gold);margin-left:8px;font-size:16px;font-weight:700;">第${s.season}赛季 · ${s.round_name}</span>
      </div>
    </div>`;
  } else if (id === 'news') {
    const newsList = (state.news || []).map((n, i) => {
      let tag = ''; let tagCls = '';
      if (i < 2) { tag = '联赛'; tagCls = 'league'; }
      else if (i < 4) { tag = '国际'; tagCls = 'world'; }
      else { tag = '个人'; tagCls = 'personal'; }
      return '<li id="news-' + i + '" onclick="expandNewsItem(\'' + pid + '\', ' + i + ', \'' + n.replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\\/g, '\\\\') + '\')"><span class="news-tag ' + tagCls + '">' + tag + '</span><span class="news-short">' + n + '</span><span class="news-detail" id="news-detail-' + i + '"><span class="loading"></span> 加载详情...</span></li>';
    }).join('') || '<li style="color:var(--text2);text-align:center;">暂无新闻</li>';
    ov.innerHTML = `<div class="modal-panel">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2>足坛大事</h2>
      <ul class="news-list">${newsList}</ul>
    </div>`;
  } else if (id === 'career') {
    ov.innerHTML = `<div class="modal-panel" style="max-width:650px;">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2>${p.name} · 生涯记录</h2>
      <div style="text-align:center;padding:40px;"><span class="loading"></span> 加载中...</div>
    </div>`;
    loadCareer(pid, ov);
  }
}

async function loadCareer(pid, ov) {
  try {
    const data = await api('GET', `/api/game/${pid}/career`);
    const records = data.career || [];
    if (records.length === 0) {
      ov.innerHTML = `<div class="modal-panel" style="max-width:650px;">
        <button class="modal-close" onclick="closeModal()">✕</button>
        <h2>${data.player_name} · 生涯记录</h2>
        <div style="text-align:center;padding:40px;color:var(--text2);">生涯刚刚开始，暂无记录<br><br>完成第一个赛季后，这里会展示每年的数据</div>
      </div>`;
      return;
    }
    const totalGoals = records.reduce((s, r) => s + (r.goals || 0), 0);
    const totalApps = records.reduce((s, r) => s + (r.appearances || 0), 0);
    const totalAssists = records.reduce((s, r) => s + (r.assists || 0), 0);
    const summaryHtml = records.length > 0 ? `
      <div class="career-summary">
        <div class="cs-total">
          ${records.length}个赛季 · 共<b>${totalApps}</b>场 · <b>${totalGoals}</b>球 · <b>${totalAssists}</b>助
        </div>
      </div>` : '';

    const cardsHtml = records.slice().reverse().map(r => {
      const honorsHtml = (r.honors || []).length > 0
        ? `<div class="c-honors">${r.honors.map(h => {
            const isGold = /冠军|金靴|最佳|欧洲/.test(h);
            return `<span class="c-honor${isGold ? ' gold' : ''}">${h}</span>`;
          }).join('')}</div>`
        : '';
      const awardsHtml = (r.awards || []).length > 0
        ? `<div class="c-honors" style="margin-top:4px;">${r.awards.map(a => {
            const isTop = /金球|MVP|最佳阵容|金童/.test(a);
            return `<span class="c-honor${isTop ? ' gold' : ''}">🏅 ${a}</span>`;
          }).join('')}</div>`
        : '';
      const hlHtml = (r.highlights || []).length > 0
        ? `<details class="c-hl"><summary>赛季大事 (${r.highlights.length}条)</summary>${r.highlights.map(h => `<div>- ${h}</div>`).join('')}</details>`
        : '';
      return `
        <div class="career-card">
          <div class="c-head">
            <span class="c-season">第${r.season}赛季</span>
            <span style="color:var(--text2);font-size:13px;">${r.age}岁</span>
            <span class="c-club">${r.club}</span>
            <span style="color:var(--text2);font-size:13px;">联赛第${r.league_position}名</span>
          </div>
          <div class="c-stats">
            <div class="c-stat"><div class="n">${r.appearances}</div><div class="l">出场</div></div>
            <div class="c-stat"><div class="n" style="color:var(--green3);">${r.goals}</div><div class="l">进球</div></div>
            <div class="c-stat"><div class="n" style="color:var(--green3);">${r.assists}</div><div class="l">助攻</div></div>
          </div>
          ${honorsHtml}
          ${awardsHtml}
          ${hlHtml}
          <div class="c-attrs">硬实力 ${r.hard_sum || 0} | 软实力 ${r.soft_sum || 0}</div>
        </div>`;
    }).join('');

    ov.innerHTML = `<div class="modal-panel" style="max-width:650px;">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2>${data.player_name} · 生涯记录</h2>
      ${summaryHtml}
      <div class="career-timeline">${cardsHtml}</div>
    </div>`;
  } catch (e) {
    ov.innerHTML = `<div class="modal-panel">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2>生涯记录</h2>
      <div style="color:var(--red);text-align:center;padding:20px;">加载失败: ${e.message}</div>
    </div>`;
  }
}

// ======================== 创建角色 ========================
function viewCreate() {
  messages = []; currentEvent = null;
  render(`
    <div id="create-wrap">
      <h1>⚽ 命运绿茵</h1>
      <div class="sub">球员生涯模拟</div>
      <div class="fg"><label>球员姓名</label><input id="c-name" value="" placeholder="输入你的名字..."></div>
      <div class="fg"><label>国籍</label><input id="c-nation" value="" placeholder="例如：中国、巴西、英格兰..."></div>
      <div class="fg"><label>加入球队（AI自动判断等级）</label><input id="c-team" value="" placeholder="例如：曼彻斯特城、国际米兰、布莱顿..."></div>
      <div class="fg"><label>场上位置</label>
        <select id="c-pos">
          <option value="中锋">中锋</option><option value="边锋">边锋</option>
          <option value="前腰">前腰</option><option value="中场" selected>中场</option><option value="后腰">后腰</option>
          <option value="边后卫">边后卫</option><option value="中后卫">中后卫</option>
        </select>
      </div>
      <div class="fg">
        <label>球员特点 <span style="font-weight:400;color:var(--text2);">（最多可选四个 · 🟢正面≤2 · 🔴负面不限）</span></label>
        <div class="trait-grid">
          ${[1,2,3,4].map(i => `
            <select id="c-trait${i}" onchange="onTraitChange(${i})">
              <option value="">无</option>
              <optgroup label="🟢 正面">
                ${POS_TRAITS.map(t => `<option value="${t}">${t}</option>`).join('')}
              </optgroup>
              <optgroup label="🔴 负面">
                ${NEG_TRAITS.map(t => `<option value="${t}">${t}</option>`).join('')}
              </optgroup>
            </select>
          `).join('')}
        </div>
        <div id="trait-desc"></div>
        <div id="trait-warn"></div>
      </div>
      <div class="fg-row">
        <div class="fg"><label>年龄 (17-35)</label><input id="c-age" type="number" min="17" max="35" value="20"></div>
        <div class="fg"><label>身高 cm (160-210)</label><input id="c-height" type="number" min="160" max="210" value="180" onchange="autoWeight()"></div>
        <div class="fg"><label>体重 kg (50-120)</label><input id="c-weight" type="number" min="50" max="120" value="75"></div>
      </div>
      <button id="create-btn" onclick="doCreate(false)">开 始 生 涯</button>
      <div style="text-align:center;margin-top:10px;">
        <button style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:12px;text-decoration:underline;" onclick="doCreate(true)">离线模式（不调用AI）</button>
      </div>
      <div style="text-align:center;margin-top:12px;">
        <button style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:13px;" onclick="viewSaves()">← 返回存档列表</button>
        <span style="margin:0 10px;color:var(--border2);">|</span>
        <button style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:12px;" onclick="resetAISetup()">⚙ 重设 AI</button>
      </div>
    </div>`);
  setTimeout(() => fillTraitDropdowns(), 50);
}

async function doCreate(fallback) {
  const btn = $('#create-btn'); btn.disabled = true; btn.innerHTML = '<span class="loading"></span>创建中...';
  try {
    const body = {
      name: $('#c-name').value || '未命名',
      nationality: $('#c-nation').value || '中国',
      team_name: $('#c-team').value || '曼彻斯特联',
      position: $('#c-pos').value,
      age: parseInt($('#c-age').value),
      height: parseInt($('#c-height').value),
      weight: parseInt($('#c-weight').value),
      traits: getSelectedTraits(),
    };
    const ep = fallback ? '/api/player/create_fallback' : '/api/player/create';
    const data = await api('POST', ep, body);
    pid = data.player.id;
    localStorage.setItem('fb_pid', pid);
    localStorage.setItem('fb_save', pid);  // 自动存档的 save_id = pid
    state = { player: data.player, season: null, events_in_queue: 0, events_completed: 0, news: [] };
    messages = [];
    await doRoundStart();
  } catch (e) {
    alert('创建失败: ' + e.message);
    btn.disabled = false; btn.innerHTML = '开 始 生 涯';
  }
}

function autoWeight() {
  const h = parseInt($('#c-height').value) || 180;
  const w = Math.round((h - 100) * 0.9);
  $('#c-weight').value = Math.max(50, Math.min(120, w));
}

const TRAIT_INFO = {
  "快马":       {type:"positive",desc:"速度飞快，冲刺能力强"},
  "铁人":       {type:"positive",desc:"体能充沛，不易受伤"},
  "空霸":       {type:"positive",desc:"制空能力极强，头球弹跳出众"},
  "盘带大师":   {type:"positive",desc:"脚下技术细腻，突破能力强"},
  "传球大师":   {type:"positive",desc:"视野开阔，传球精准"},
  "门前杀手":   {type:"positive",desc:"射术精湛，进球嗅觉敏锐"},
  "防守铁闸":   {type:"positive",desc:"防守意识强，抢断站位出色"},
  "任意球大师": {type:"positive",desc:"定位球功夫一流"},
  "领袖":       {type:"positive",desc:"天生队长，团队凝聚力强"},
  "大心脏":     {type:"positive",desc:"关键时刻沉着冷静"},
  "野兽":       {type:"positive",desc:"身体对抗强硬，斗志旺盛"},
  "宠儿":       {type:"positive",desc:"人缘好，受媒体和球迷喜爱"},
  "节拍器":     {type:"positive",desc:"中场大脑，控制比赛节奏"},
  "全能":       {type:"positive",desc:"不拘一格，各方面均衡发展"},
  "远射重炮":   {type:"positive",desc:"禁区外远程发炮，门将噩梦"},
  "带刀侍卫":   {type:"positive",desc:"后卫也能进球，定位球头槌好手"},
  "老油条":     {type:"positive",desc:"经验丰富，关键时刻不犯错"},
  "攻守兼备":   {type:"positive",desc:"攻防两端都能做出贡献"},
  "勤勉":       {type:"positive",desc:"训练刻苦，从不懈怠"},
  "天残脚":     {type:"negative",desc:"非惯用脚基本只能用来站立"},
  "争议人物":   {type:"negative",desc:"嘴没把门，媒体最爱的话题人物"},
  "玻璃人":     {type:"negative",desc:"天赋异禀但身体脆弱易伤"},
  "刺头":       {type:"negative",desc:"训练迟到顶撞教练，但个人能力出众"},
  "独狼":       {type:"negative",desc:"拿到球就自己干，不传"},
  "神经刀":     {type:"negative",desc:"一场超神一场超鬼，发挥极不稳定"},
  "慵懒":       {type:"negative",desc:"能坐着绝不站着，训练总偷懒"},
  "轮椅人":     {type:"negative",desc:"转身如航母掉头，加速跑过中老年"},
};
const TRAIT_KEYS = Object.keys(TRAIT_INFO);
const POS_TRAITS = TRAIT_KEYS.filter(k => TRAIT_INFO[k].type === "positive");
const NEG_TRAITS = TRAIT_KEYS.filter(k => TRAIT_INFO[k].type === "negative");

function fillTraitDropdowns() {
  for (let i = 1; i <= 4; i++) {
    const el = $(`#c-trait${i}`);
    if (!el) continue;
    el.innerHTML = '<option value="">无特点</option>';
    [...POS_TRAITS, null, ...NEG_TRAITS].forEach(k => {
      if (k === null) { el.innerHTML += '<option disabled>── 负面特点 ──</option>'; return; }
      const info = TRAIT_INFO[k];
      const icon = info.type === 'negative' ? '🔴' : '🟢';
      el.innerHTML += `<option value="${k}">${icon} ${k}</option>`;
    });
    el.onchange = () => onTraitChange(i);
  }
}

function onTraitChange(which) {
  const sel = [];
  for (let i = 1; i <= 4; i++) {
    const v = $(`#c-trait${i}`)?.value;
    if (v) sel.push(v);
  }
  const posCount = sel.filter(t => TRAIT_INFO[t]?.type === "positive").length;
  const atPosLimit = posCount >= 2;
  for (let i = 1; i <= 4; i++) {
    const el = $(`#c-trait${i}`);
    if (!el) continue;
    const curVal = el.value;
    el.className = '';
    if (curVal && TRAIT_INFO[curVal]?.type === 'positive') el.className = 'has-pos';
    if (curVal && TRAIT_INFO[curVal]?.type === 'negative') el.className = 'has-neg';
    el.querySelectorAll('option').forEach(opt => {
      if (!opt.value) return;
      const isPos = TRAIT_INFO[opt.value]?.type === "positive";
      const alreadySelected = sel.includes(opt.value) && opt.value !== curVal;
      opt.disabled = alreadySelected || (isPos && atPosLimit && opt.value !== curVal);
    });
  }
  const uniq = [...new Set(sel)];
  $('#trait-desc').innerHTML = uniq.map(t => {
    const info = TRAIT_INFO[t];
    const icon = info?.type === "negative" ? "🔴" : "🟢";
    return `${icon} ${t}：${info?.desc || ""}`;
  }).join('<br>');
  $('#trait-warn').innerHTML = posCount > 2 ? '⚠ 正面特点最多2个' : '';
}

function getSelectedTraits() {
  const sel = [];
  for (let i = 1; i <= 4; i++) {
    const v = $(`#c-trait${i}`)?.value;
    if (v) sel.push(v);
  }
  return [...new Set(sel)];
}

setTimeout(() => { if ($('#c-trait1')) fillTraitDropdowns(); }, 100);

// ======================== 回合开始 ========================
async function doRoundStart() {
  addSys('⏳ 新回合开始...');
  renderGame();
  try {
    const data = await api('POST', `/api/game/${pid}/round_start`);
    // refresh state
    state = await api('GET', `/api/game/${pid}/state`);
    state.news = data.news;
    pendingOffers = [];
    messages = [];
    addSys(`━━━ 第${data.season}赛季 · ${data.round_name} ━━━`);
    if (data.round_intro) addIntro(data.round_intro);
    (data.news || []).forEach(n => addNews(n));
    addSys('点击下方按钮获取事件 ↓');
    messages.push(`<div class="btn-row" id="first-event-btn">
      <button class="action-btn btn-primary" onclick="fetchNextEvent()">获取事件</button>
    </div>`);
    // 同步新闻到 state
    if (!state.news || state.news.length === 0) state.news = data.news;
    renderGame();
  } catch (e) {
    addSys('❌ ' + e.message);
    renderGame();
  }
}

// ======================== 获取下一个事件 ========================
async function fetchNextEvent() {
  // 移除旧事件卡片
  messages = messages.filter(m => !m.includes('evt-card'));
  const btnRow = messages.findIndex(m => m.includes('next-event-btn') || m.includes('settle-btn-row') || m.includes('first-event-btn'));
  if (btnRow >= 0) messages.splice(btnRow, 1);

  addSys('⏳ 生成事件...');
  renderGame();
  try {
    const data = await api('POST', `/api/game/${pid}/next_event`);
    messages = messages.filter(m => m !== '⏳ 生成事件...' && !m.includes('点击下方按钮获取事件'));
    addEventCard(data.event);
    addSys(`事件 ${data.events_done + 1} / ${data.events_total}`);
    renderGame();
  } catch (e) {
    messages = messages.filter(m => m !== '⏳ 生成事件...' && !m.includes('点击下方按钮获取事件'));
    addSys('❌ ' + e.message);
    renderGame();
  }
}

// ======================== 事件选择 ========================
async function chooseOpt(optId) {
  disableEventBtns();
  messages = messages.filter(m => !m.includes('evt-card'));
  const phId = 's-' + Date.now();
  messages.push(`<div class="msg ai" id="${phId}"></div>`);
  renderGame();
  try {
    const result = await apiStream(
      `/api/game/${pid}/event_choice/stream`,
      { option_id: optId, custom_text: '' },
      (chunk) => { const el = document.getElementById(phId); if (el) { el.textContent += chunk; scrollDown(); } }
    );
    const idx = messages.findIndex(m => m.includes(phId));
    if (idx >= 0) messages[idx] = `<div class="msg ai">${result.narrative}</div>`;
    if (result.transfer_offers && result.transfer_offers.length > 0) {
      addSys(`📨 收到 ${result.transfer_offers.length} 份转会报价，点击顶栏报价按钮查看`);
      pendingOffers = result.transfer_offers;
    }
    state = await api('GET', `/api/game/${pid}/state`);
    currentEvent = null;
    handleNewAchievements(result.new_achievements);
    showAfterEvent(result.events_done, result.events_total);
    renderGame();
  } catch (e) {
    messages = messages.filter(m => !m.includes(phId));
    addSys('❌ ' + e.message); renderGame();
  }
}

let negoChatLog = [];  // 谈判对话历史

async function doNegotiate(idx) {
  const msgEl = document.getElementById(`nego-msg-${idx}`);
  const msg = msgEl?.value?.trim();
  if (!msg) return;
  const logEl = document.getElementById(`nego-log-${idx}`);
  negoChatLog.push({role:'player', text:msg});
  if (logEl) {
    logEl.innerHTML += `<div style="color:var(--green3);margin:4px 0;">🧑 ${msg}</div>`;
    logEl.scrollTop = logEl.scrollHeight;
  }
  msgEl.value = '';
  try {
    const res = await api('POST', `/api/game/${pid}/transfer/negotiate`, { content: msg, target: '' });
    if (logEl) {
      logEl.innerHTML += `<div style="color:var(--gold);margin:4px 0;">🏢 ${res.narrative}</div>`;
      logEl.scrollTop = logEl.scrollHeight;
    }
    if (res.offer) {
      pendingOffers[idx] = res.offer;
      const o = res.offer;
      if (res.decision === 'reject') {
        pendingOffers.splice(idx, 1); closeModal(); addSys('谈判破裂，报价撤回'); renderGame(); return;
      }
      // 内联更新报价数字，不重建整个界面
      const wageEl = document.getElementById(`nego-wage-${idx}`);
      const yearEl = document.getElementById(`nego-year-${idx}`);
      const clEl = document.getElementById(`nego-clause-${idx}`);
      const yrSalary = document.getElementById(`nego-yrsalary-${idx}`);
      if (wageEl) wageEl.textContent = o.wage;
      if (yearEl) yearEl.textContent = o.years;
      if (clEl) clEl.textContent = o.clause > 0 ? o.clause + ' 万欧' : '无';
      if (yrSalary) yrSalary.textContent = Math.round(o.wage * 52);
    }
    if (res.round >= 4 && logEl) logEl.innerHTML += '<div style="color:var(--red);">已达最大谈判轮次</div>';
  } catch(e) { if (logEl) logEl.innerHTML += `<div style="color:var(--red);">失败: ${e.message}</div>`; }
}

function openTransferOffers() {
  if (!pendingOffers || pendingOffers.length === 0) return;
  closeModal();
  const ov = document.createElement('div');
  ov.className = 'modal-overlay'; ov.id = 'modal-overlay';
  ov.onclick = e => { if (e.target === ov) closeModal(); };
  const tierStars = {'豪门':'5星','劲旅':'4星','中游':'3星','下游':'2星','弱旅':'1星'};
  const listHtml = pendingOffers.map((o, i) => `
    <div style="background:var(--bg2);border:1px solid var(--border2);border-radius:8px;padding:14px;margin-bottom:8px;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <div>
          <span style="font-size:16px;font-weight:700;color:var(--gold);">${o.team}</span>
          <span style="color:var(--text2);margin-left:6px;font-size:13px;">${o.tier||''} ${tierStars[o.tier]||''}</span>
        </div>
        <div style="display:flex;gap:6px;">
          <button class="save-btn cont" onclick="showNegotiation(${i})" style="font-size:12px;">谈判</button>
          <button class="save-btn cont" onclick="acceptTransferOffer(${i})" style="font-size:12px;background:var(--green2);">签约</button>
          <button class="save-btn del" onclick="rejectTransferOffer(${i})" style="font-size:12px;">拒绝</button>
        </div>
      </div>
      <div style="margin-top:6px;font-size:13px;color:var(--text2);">
        周薪 ${o.wage} 万 · ${o.years} 年${o.clause > 0 ? ' · 解约金 ' + o.clause + '万' : ''}${o.is_renewal ? ' · 续约' : ''}
      </div>
    </div>
  `).join('');
  ov.innerHTML = `<div class="modal-panel" style="max-width:550px;">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <h2>📨 转会报价 (${pendingOffers.length})</h2>
    ${listHtml}
  </div>`;
  document.body.appendChild(ov);
}

function showNegotiation(idx) {
  if (idx >= pendingOffers.length) { closeModal(); renderGame(); return; }
  const o = pendingOffers[idx];
  closeModal();
  const ov = document.createElement('div');
  ov.className = 'modal-overlay'; ov.id = 'modal-overlay';
  const tierStars = {'豪门':'5星','劲旅':'4星','中游':'3星','下游':'2星','弱旅':'1星'};
  ov.innerHTML = `<div class="modal-panel talk-modal-content">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <h2>📝 ${o.is_renewal ? '续约谈判' : '合同谈判'}</h2>
    <div style="text-align:center;padding:12px 0;">
      <div style="font-size:26px;font-weight:700;color:var(--gold);">${o.team}</div>
      <div style="color:var(--text2);">${o.tier||''} ${tierStars[o.tier]||''} · ${o.league||''}</div>
    </div>
    <div style="background:var(--bg2);border-radius:8px;padding:14px;margin:10px 0;">
      <div style="display:flex;justify-content:space-between;padding:5px 0;"><span>合同年限</span><b style="color:var(--text3);" id="nego-year-${idx}">${o.years} 年</b></div>
      <div style="display:flex;justify-content:space-between;padding:5px 0;"><span>周薪</span><b style="color:var(--gold);" id="nego-wage-${idx}">${o.wage} 万欧</b></div>
      <div style="display:flex;justify-content:space-between;padding:5px 0;"><span>年薪</span><b style="color:var(--text3);" id="nego-yrsalary-${idx}">${Math.round(o.wage * 52)} 万欧</b></div>
      <div style="display:flex;justify-content:space-between;padding:5px 0;"><span>解约金</span><b style="color:var(--green3);" id="nego-clause-${idx}">${o.clause > 0 ? o.clause + ' 万欧' : '无'}</b></div>
    </div>
    <div id="nego-area-${idx}" style="margin-top:8px;">
      <textarea id="nego-msg-${idx}" class="talk-msg-input" style="min-height:50px;font-size:14px;" placeholder="输入你的谈判要求...（例：周薪再高点，我要10万）"></textarea>
      <div style="display:flex;gap:6px;margin-top:6px;">
        <button class="talk-send-btn" onclick="doNegotiate(${idx})" style="flex:1;font-size:13px;">💬 谈判</button>
        <button class="talk-send-btn" onclick="acceptTransferOffer(${idx})" style="flex:1;font-size:13px;background:var(--green2);">✓ 签约</button>
        <button class="talk-send-btn" onclick="rejectTransferOffer(${idx})" style="flex:1;font-size:13px;background:transparent;border:1px solid var(--red);color:var(--red);">✕ 拒绝</button>
      </div>
    </div>
    <div id="nego-log-${idx}" style="margin-top:8px;font-size:13px;color:var(--text2);max-height:120px;overflow-y:auto;"></div>
    ${pendingOffers.length > 1 ? `<div style="text-align:center;margin-top:10px;font-size:12px;color:var(--text2);">报价 ${idx+1}/${pendingOffers.length}</div>` : ''}
  </div>`;
  document.body.appendChild(ov);
}

async function acceptTransferOffer(idx) {
  closeModal();
  try {
    await api('POST', `/api/game/${pid}/transfer/accept`, { content: String(idx), target: '' });
    // 签约后清空所有其他报价
    pendingOffers = [];
    addSys('✅ 签约成功！');
    state = await api('GET', `/api/game/${pid}/state`);
    renderGame();
  } catch(e) { alert('签约失败: ' + e.message); }
}

async function rejectTransferOffer(idx) {
  try {
    await api('POST', `/api/game/${pid}/transfer/reject`, { content: String(idx), target: '' });
    pendingOffers.splice(idx, 1);
    if (pendingOffers.length === 0) { closeModal(); renderGame(); }
    else { showNegotiation(0); }
  } catch(e) { alert('操作失败: ' + e.message); }
}

async function chooseCustom() {
  const t = prompt('请输入自定义行动：');
  if (!t) return;
  disableEventBtns();
  messages = messages.filter(m => !m.includes('evt-card'));
  addPlayer(`【自定义】${t}`);
  const phId = 's-' + Date.now();
  messages.push(`<div class="msg ai" id="${phId}"></div>`);
  renderGame();
  try {
    const result = await apiStream(
      `/api/game/${pid}/event_choice/stream`,
      { option_id: 'custom', custom_text: t },
      (chunk) => { const el = document.getElementById(phId); if (el) { el.textContent += chunk; scrollDown(); } }
    );
    const idx = messages.findIndex(m => m.includes(phId));
    if (idx >= 0) messages[idx] = `<div class="msg ai">${result.narrative}</div>`;
    if (result.transfer_offers && result.transfer_offers.length > 0) {
      addSys(`📨 收到 ${result.transfer_offers.length} 份转会报价`);
      pendingOffers = result.transfer_offers;
    }
    state = await api('GET', `/api/game/${pid}/state`);
    currentEvent = null;
    handleNewAchievements(result.new_achievements);
    showAfterEvent(result.events_done, result.events_total);
    renderGame();
  } catch (e) {
    messages = messages.filter(m => !m.includes(phId));
    addSys('❌ ' + e.message); renderGame();
  }
}

function disableEventBtns() {
  const card = document.getElementById('evt-card');
  if (card) card.querySelectorAll('button').forEach(b => b.disabled = true);
}

function showAfterEvent(done, total) {
  const left = total - done;
  if (left > 0) {
    messages.push(`<div class="btn-row" id="next-event-btn">
      <button class="action-btn btn-primary" onclick="fetchNextEvent()">下一个事件 (${left}剩余)</button>
      <button class="action-btn btn-gold" onclick="doSettle()">回合结算</button>
    </div>`);
  } else {
    messages.push(`<div class="btn-row" id="settle-btn-row">
      <span style="color:var(--gold)">本回合事件已全部完成</span>
      <button class="action-btn btn-gold" onclick="doSettle()">回合结算</button>
    </div>`);
  }
}

// ======================== 自由对话 ========================
function openTalkModal() {
  closeModal();
  const ov = document.createElement('div');
  ov.className = 'modal-overlay';
  ov.id = 'modal-overlay';
  ov.onclick = e => { if (e.target === ov) closeModal(); };
  ov.innerHTML = `
    <div class="modal-panel talk-modal-content">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2>💬 自由对话</h2>
      <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px;">对话对象</label>
      <select id="talk-person">
        <option value="主教练">主教练</option>
        <option value="队友">队友</option>
        <option value="经纪人">经纪人</option>
        <option value="家人">家人</option>
        <option value="记者">记者</option>
        <option value="俱乐部高层">俱乐部高层</option>
        <option value="球迷">球迷</option>
        <option value="其他">其他（在内容中说明）</option>
      </select>
      <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:4px;">你想说什么</label>
      <textarea id="talk-msg" class="talk-msg-input" placeholder="输入你想说的话..."></textarea>
      <button id="talk-send" class="talk-send-btn" onclick="doTalk()">发 送</button>
    </div>`;
  document.body.appendChild(ov);
  setTimeout(() => document.getElementById('talk-msg')?.focus(), 200);
}

async function doTalk() {
  const txt = document.getElementById('talk-msg')?.value?.trim();
  if (!txt) return;
  const person = document.getElementById('talk-person')?.value || '某人';
  const btn = document.getElementById('talk-send');
  if (btn) { btn.disabled = true; btn.textContent = '发送中...'; }

  closeModal();
  addPlayer(`【${person}】${txt}`);
  const phId = 's-' + Date.now();
  messages.push(`<div class="msg ai" id="${phId}"></div>`);
  renderGame();

  try {
    const result = await apiStream(
      `/api/game/${pid}/free_talk/stream`,
      { content: txt, target: person },
      (chunk) => { const el = document.getElementById(phId); if (el) { el.textContent += chunk; scrollDown(); } }
    );
    const idx = messages.findIndex(m => m.includes(phId));
    if (idx >= 0) messages[idx] = `<div class="msg ai">${result.narrative}</div>`;
    state = await api('GET', `/api/game/${pid}/state`);
    renderGame();
  } catch (e) {
    messages = messages.filter(m => !m.includes(phId));
    addSys('❌ ' + e.message);
    renderGame();
  }
}

// ======================== 结算 ========================
async function doSettle() {
  if (!confirm('确定结算当前回合吗？')) return;
  messages = messages.filter(m => !m.includes('next-event-btn') && !m.includes('settle-btn-row') && !m.includes('first-event-btn'));
  addSys('⏳ 结算中...');
  $('#settle-btn').disabled = true;
  renderGame();
  try {
    const data = await api('POST', `/api/game/${pid}/settle`);
    messages = messages.filter(m => m !== '⏳ 结算中...');
    addSettle(data);
    state = await api('GET', `/api/game/${pid}/state`);
    handleNewAchievements(data.new_achievements);
    renderGame();
  } catch (e) { addSys('❌ '+e.message); renderGame(); }
  $('#settle-btn').disabled = false;
}

// ======================== 渲染 ========================
function renderGame() {
  if (!state) return;
  const p = state.player; const s = state.season || {};
  render(`
    <div id="topbar">
      <div>
        <div class="title">⚽ 命运绿茵</div>
        <div class="info">${p.name}<span>|</span>${p.nationality}<span>|</span>${p.position}<span>|</span>${p.team_name}<span>|</span>世界${p.team_tier}<span>|</span>${p.locker_status||'普通成员'}<span>|</span>${p.height}cm ${p.weight}kg</div>
      </div>
      <div class="top-btns">
        <button class="top-btn" onclick="openModal('attrs')">📊 属性</button>
        <button class="top-btn" onclick="openModal('career')">🏆 生涯</button>
        <button class="top-btn" onclick="openAchievements()">🎖 成就</button>
        <button class="top-btn" onclick="openSaveModal()">💾 保存</button>
        <button class="top-btn" onclick="openModal('team')">🏟 球队</button>
        <button class="top-btn" onclick="openModal('news')">📰 新闻</button>
        ${pendingOffers.length > 0 ? '<button class="top-btn" style="color:var(--gold);border-color:var(--gold);" onclick="openTransferOffers()">📨 报价(' + pendingOffers.length + ')</button>' : ''}
        <button class="top-btn back-menu-btn" onclick="doBackToMenu()">🏠 菜单</button>
        <button class="top-btn back-menu-btn" onclick="resetAISetup()" style="margin-right:4px;">⚙</button>
      </div>
      <div style="font-size:11px;color:var(--text2);text-align:right;">第${s.season||'?'}赛季<br>${s.round_name||''}</div>
    </div>
    <div id="main-area">${renderMsgs()}</div>
    <div id="input-area">
      <button class="action-btn btn-gold" onclick="openTalkModal()" style="font-size:14px;">💬 自由对话</button>
      <button id="settle-btn" onclick="doSettle()">结算</button>
    </div>`);
  scrollDown();
}


// ======================== 存档选择 ========================
async function viewSaves() {
  pid = null; state = null; messages = []; currentEvent = null;

  let saves = [];
  try { const r = await api('GET', '/api/saves'); saves = r.saves || []; } catch (e) {}

  if (saves.length === 0) {
    viewCreate();
    return;
  }

  saves.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  const cards = saves.map(s => `
    <div class="save-card">
      <div class="s-avatar">${s.slot_name === '自动存档' ? '💾' : '📁'}</div>
      <div class="s-info">
        <div class="s-name">${s.slot_name}</div>
        <div class="s-meta">
          <b>${s.name}</b><span>|</span>${s.position}<span>|</span>${s.team_name}<span>|</span>
          第${s.season}赛季 · ${s.round_name}
        </div>
      </div>
      <div class="s-actions">
        <button class="save-btn cont" onclick="doContinue('${s.save_id}')">继续</button>
        <button class="save-btn del" onclick="doDeleteSave('${s.save_id}')">删除</button>
      </div>
    </div>`).join('');

  render(`
    <div class="save-list" style="padding-top:40px;">
      <h1>⚽ 命运绿茵</h1>
      <div class="sub">球员生涯模拟</div>
      ${cards}
      <button class="new-game-btn" onclick="viewCreate()">＋ 创建新角色</button>
      <div style="text-align:center;margin-top:12px;"><button style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:12px;" onclick="resetAISetup()">⚙ 重设 AI 配置</button></div>
    </div>`);
}

async function doContinue(saveId) {
  try {
    const data = await api('POST', `/api/saves/${saveId}/load`);
    pid = data.player.id;
    localStorage.setItem('fb_save', saveId);
    localStorage.setItem('fb_pid', pid);
    state = await api('GET', `/api/game/${pid}/state`);
    restoreGameState();
  } catch (e) {
    alert('加载失败: ' + e.message);
    viewSaves();
  }
}

// ---- 根据已保存状态恢复游戏界面 ----
function restoreGameState() {
  const s = state.season || {};
  messages = [];
  addSys(`欢迎回来，${state.player.name}`);
  addSys(`第${s.season}赛季 · ${s.round_name}`);

  const done = state.events_completed || 0;
  const evt = state.current_event;

  if (evt) {
    // 有待处理的事件卡片
    addEventCard(evt);
    addSys(`事件 ${done + 1} / 4`);
  } else if (done >= 4 || state.can_settle) {
    // 事件已完成，提示结算
    addSys('本回合事件已全部完成');
    messages.push(`<div class="btn-row" id="settle-btn-row">
      <span style="color:var(--gold)">本回合事件已全部完成</span>
      <button class="action-btn btn-gold" onclick="doSettle()">回合结算</button>
    </div>`);
  } else if (state.can_get_event) {
    // 新回合或事件可获取
    addSys('点击获取事件继续游戏 ↓');
    messages.push(`<div class="btn-row" id="first-event-btn">
      <button class="action-btn btn-primary" onclick="fetchNextEvent()">获取事件</button>
      ${done > 0 ? `<button class="action-btn btn-gold" onclick="doSettle()">回合结算</button>` : ''}
    </div>`);
  }

  renderGame();
}

async function doDeleteSave(saveId) {
  if (!confirm('确定删除这个存档吗？此操作不可恢复。')) return;
  try { await api('DELETE', `/api/saves/${saveId}`); } catch (e) { alert('删除失败: ' + e.message); }
  if (saveId === localStorage.getItem('fb_save')) {
    localStorage.removeItem('fb_save'); localStorage.removeItem('fb_pid');
  }
  viewSaves();
}

async function expandNewsItem(p, i, headline) {
  const li = document.getElementById('news-' + i);
  const detail = document.getElementById('news-detail-' + i);
  if (!li || !detail) return;
  if (li.classList.contains('open')) { li.classList.remove('open'); return; }
  li.classList.add('open');
  if (detail.dataset.loaded === '1') return;
  try {
    const res = await api('POST', '/api/game/' + p + '/news/expand', { content: headline, target: '' });
    detail.textContent = res.detail;
    detail.dataset.loaded = '1';
  } catch(e) {
    detail.textContent = '详情加载失败';
  }
}

// ---- 成就系统 ----
function showAchievementBanner(ach) {
  const b = document.createElement('div');
  b.className = 'ach-banner';
  b.innerHTML = `<span class="ach-icon">${ach.icon}</span><div class="ach-text">🏆 成就解锁！<b>${ach.name}</b><small>${ach.desc}</small></div>`;
  document.body.appendChild(b);
  setTimeout(() => b.remove(), 4000);
}

async function openAchievements() {
  closeModal();
  const ov = document.createElement('div');
  ov.className = 'modal-overlay'; ov.id = 'modal-overlay';
  ov.onclick = e => { if (e.target === ov) closeModal(); };
  ov.innerHTML = `<div class="modal-panel" style="max-width:700px;">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <h2>🏆 成就</h2>
    <div style="text-align:center;padding:40px;"><span class="loading"></span> 加载中...</div>
  </div>`;
  document.body.appendChild(ov);

  try {
    const data = await api('GET', `/api/game/${pid}/achievements`);
    const all = data.achievements || [];
    const cats = ['里程碑','荣誉','事件','巅峰','更衣室','合同','转会','特点'];
    const unlocked = all.filter(a => a.unlocked).length;
    const total = all.length;

    const html = cats.map(cat => {
      const items = all.filter(a => a.cat === cat);
      const u = items.filter(a => a.unlocked).length;
      const itemsHtml = items.map(a => `
        <div class="ach-item ${a.unlocked ? 'unlocked' : 'locked'}">
          <span class="ach-icon">${a.icon}</span>
          <div class="ach-info">
            <div class="ach-name">${a.name}</div>
            <div class="ach-desc">${a.unlocked ? `第${a.season}赛季 ${a.round} 解锁` : a.desc}</div>
          </div>
        </div>`).join('');
      return `<div class="ach-cat"><h3>${cat} <span class="ach-count">${u}/${items.length}</span></h3><div class="ach-grid">${itemsHtml}</div></div>`;
    }).join('');

    ov.innerHTML = `<div class="modal-panel" style="max-width:700px;">
      <button class="modal-close" onclick="closeModal()">✕</button>
      <h2>🏆 成就 <span style="font-size:14px;color:var(--text2);font-weight:400;">${unlocked}/${total}</span></h2>
      ${html}
    </div>`;
  } catch (e) {
    ov.innerHTML = `<div class="modal-panel"><button class="modal-close" onclick="closeModal()">✕</button><h2>成就</h2><div style="color:var(--red);padding:20px;">加载失败</div></div>`;
  }
}

function handleNewAchievements(list) {
  if (!list || list.length === 0) return;
  list.forEach(a => setTimeout(() => showAchievementBanner(a), list.indexOf(a) * 500));
}

function doBackToMenu() {
  if (!confirm('返回主菜单？\n当前进度已自动保存，下次可从存档列表继续。')) return;
  viewSaves();
}

// ---- 手动命名存档 ----
function openSaveModal() {
  closeModal();
  const ov = document.createElement('div');
  ov.className = 'modal-overlay'; ov.id = 'modal-overlay';
  ov.onclick = e => { if (e.target === ov) closeModal(); };
  ov.innerHTML = `<div class="modal-panel talk-modal-content">
    <button class="modal-close" onclick="closeModal()">✕</button>
    <h2>💾 保存游戏</h2>
    <label style="font-size:12px;color:var(--text2);display:block;margin-bottom:6px;">存档名称</label>
    <input id="save-name" class="talk-msg-input" style="min-height:auto;height:44px;" placeholder="例：欧冠决赛前" value="">
    <button class="talk-send-btn" onclick="doManualSave()" style="margin-top:8px;">保 存</button>
  </div>`;
  document.body.appendChild(ov);
  setTimeout(() => document.getElementById('save-name')?.focus(), 200);
}

async function doManualSave() {
  const name = document.getElementById('save-name')?.value?.trim() || '手动存档';
  const btn = document.querySelector('.talk-send-btn');
  if (btn) { btn.disabled = true; btn.textContent = '保存中...'; }
  try {
    const data = await api('POST', `/api/game/${pid}/save`, { content: name });
    closeModal();
    addSys(`💾 存档「${name}」已保存`);
    renderGame();
  } catch (e) {
    alert('保存失败: ' + e.message);
    if (btn) { btn.disabled = false; btn.textContent = '保 存'; }
  }
}

// ======================== AI 设置 ========================
async function checkAISetup() {
  try { const r = await api('GET', '/api/config'); return r.ai_ready; } catch(e) { return false; }
}

function showSetup() {
  render(`
    <div class="save-list" style="padding-top:30px;">
      <h1 style="font-size:28px;">⚽ 命运绿茵</h1>
      <div class="sub" style="margin-bottom:20px;">首次使用请配置 AI 接口</div>
      <div class="fg"><label>API Key（必填）</label><input id="setup-key" placeholder="sk-..." value=""></div>
      <div class="fg"><label>API 地址</label><input id="setup-url" placeholder="https://api.deepseek.com" value=""></div>
      <div class="fg"><label>模型名称</label><input id="setup-model" placeholder="deepseek-chat" value=""></div>
      <button id="create-btn" onclick="doSetup()" style="margin-top:12px;">保 存 并 测 试</button>
      <div id="setup-msg" style="text-align:center;margin-top:10px;font-size:13px;color:var(--text2);"></div>
    </div>
  `);
}

async function resetAISetup() {
  localStorage.removeItem('fb_ai_setup');
  await api('POST', '/api/setup', { api_key: '', base_url: '', model: '' });
  location.reload();
}

async function doSetup() {
  const btn = $('#create-btn'); btn.disabled = true; btn.innerHTML = '<span class="loading"></span>测试中...';
  const msg = $('#setup-msg');
  try {
    await api('POST', '/api/setup', {
      api_key: $('#setup-key').value.trim(),
      base_url: $('#setup-url').value.trim(),
      model: $('#setup-model').value.trim(),
      test: true,
    });
    localStorage.setItem('fb_ai_setup', JSON.stringify({
      api_key: $('#setup-key').value.trim(),
      base_url: $('#setup-url').value.trim(),
      model: $('#setup-model').value.trim(),
    }));
    msg.innerHTML = '✅ 配置成功！加载中...';
    setTimeout(() => init(), 500);
  } catch(e) {
    msg.innerHTML = '❌ 连接失败: ' + e.message;
    btn.disabled = false; btn.innerHTML = '保 存 并 测 试';
  }
}

// ======================== 初始化 ========================
async function init() {
  // 检查 AI 配置
  const ready = await checkAISetup();
  if (!ready) {
    const saved = localStorage.getItem('fb_ai_setup');
    if (saved) {
      try {
        await api('POST', '/api/setup', JSON.parse(saved));
        if (!(await checkAISetup())) { showSetup(); return; }
      } catch(e) { showSetup(); return; }
    } else { showSetup(); return; }
  }

  let saves = [];
  try { const r = await api('GET', '/api/saves'); saves = r.saves || []; } catch (e) {}

  // 优先用 save_id，回退到 player_id 查找
  const savedSave = localStorage.getItem('fb_save');
  const savedPid = localStorage.getItem('fb_pid');
  const match = (savedSave && saves.find(s => s.save_id === savedSave))
             || (savedPid && saves.find(s => s.player_id === savedPid && s.slot_name === '自动存档'));

  if (match) {
    try {
      const data = await api('POST', `/api/saves/${match.save_id}/load`);
      pid = data.player.id;
      localStorage.setItem('fb_save', match.save_id);
      localStorage.setItem('fb_pid', pid);
      state = await api('GET', `/api/game/${pid}/state`);
      restoreGameState();
      return;
    } catch (e) { localStorage.removeItem('fb_save'); localStorage.removeItem('fb_pid'); }
  }

  if (saves.length > 0) { viewSaves(); } else { viewCreate(); }
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
init();
