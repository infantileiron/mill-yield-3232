import {table} from '../components/common/table.js';
import {badge} from '../components/common/status.js';
import {esc,fmt,canEdit} from '../utils/format.js';

const statusNames={draft:'草稿',published:'已发布'};
const sheetStatus=value=>`<span class="badge ${value==='published'?'approved':''}">${statusNames[value]||esc(value)}</span>`;
const stamp=v=>esc(String(v||'').replace('T',' ').replace('+00:00','').slice(0,16));

function pointsText(points){return (points||[]).map(p=>`${fmt(p.reading)}→${fmt(p.standard)}`).join(' · ');}

function draftForm(editable){
  return `<form id="calibration-form">
    <label>校准单编号<input name="code" required minlength="3" pattern="[A-Za-z0-9_-]+" value="CAL-1115-V3"></label>
    <div class="form-row">
      <label>生效开始（UTC）<input name="effective_from" type="datetime-local" required value="2026-11-20T00:00"></label>
      <label>生效结束（UTC）<input name="effective_to" type="datetime-local" required value="2026-11-30T00:00"></label>
    </div>
    <label>读数 / 标准值对照点（每行“读数,标准值”）<textarea name="points" required placeholder="70.0,71.0&#10;75.0,76.0">70.0,71.0
75.0,76.0
80.0,81.2</textarea></label>
    <label>校准说明<input name="note" value="换标后对照"></label>
    <button class="primary" ${editable?'':'disabled'}>保存草稿 +</button>
  </form>`;
}

function parsePoints(text){
  return String(text||'').split('\n').map(line=>line.trim()).filter(Boolean).map(line=>{
    const [reading,standard]=line.split(/[,，\s]+/).map(Number);
    if(!Number.isFinite(reading)||!Number.isFinite(standard))throw Error('对照点格式应为“读数,标准值”，每行一个');
    return {reading,standard};
  });
}

export const calibrationFormData=data=>({
  code:data.code,
  effective_from:new Date(data.effective_from+'Z').toISOString(),
  effective_to:new Date(data.effective_to+'Z').toISOString(),
  points:parsePoints(data.points),
  note:data.note||'',
});

const basisText=basis=>{
  if(!basis||typeof basis!=='object')return basis?esc(String(basis)):'';
  const lo=basis.lower||{},hi=basis.upper||{};
  return `${fmt(lo.reading)}→${fmt(lo.standard)} / ${fmt(hi.reading)}→${fmt(hi.standard)}（权重 ${fmt(basis.weight,3)}）`;
};

function previewPanel(preview){
  if(!preview)return `<div class="empty">选择一张草稿校准单，预览受影响的仪器样本与换算依据。手录旧样本不参与换算。</div>`;
  const rows=preview.samples.map(s=>[
    `<strong>${esc(s.sample_code)}</strong><small>${esc(s.batch_code||'')}</small>`,
    esc(s.line),stamp(s.sampled_at),fmt(s.original_yield)+'%',
    s.blocked?`<span class="rust">受阻</span>`:`<strong>${fmt(s.converted_yield)}%</strong>`,
    s.blocked?`<small class="rust">${esc(s.reason||'')}</small>`:(s.calibration?.sheet_code?`${esc(s.calibration.sheet_code)}<small>${basisText(s.calibration.basis)}</small>`:'—'),
  ]);
  const conflict=preview.conflicts?.length?`<div class="notice error" style="position:static">时段与已发布校准单 ${esc(preview.conflicts.join('、'))} 重叠：命中重叠时段的样本会让整次诊断受阻。</div>`:'';
  return `<div class="section-head"><h2>影响样本预览</h2><span>${preview.affected_count} 个仪器样本 / ${preview.blocked_count} 个受阻</span></div>
    ${conflict}
    <p class="hint">手录样本 ${preview.manual_ignored} 条沿用原值。换算口径：按采样时刻命中时段，再在对照点之间分段线性插值；超出对照范围即受阻。</p>
    ${table(['样本 / 批次','产线','采样时刻','原值','换算值','校准依据'],rows)}`;
}

export function calibrationsPage(s){
  const selected=s.calibrationPreview;
  return `<header><p class="eyebrow">03 / INSTRUMENT CALIBRATION</p><h1>仪器校准单</h1><p>换标不覆写原始读数。发布后按采样时刻选择校准单，把仪器读数分段线性换算为出粉率；手录旧样本沿用原值。</p></header>
  <div class="workspace"><section class="paper">
    <h2>新建校准单草稿</h2>
    ${draftForm(canEdit(s.user))}
    <p class="hint">发布需质量负责人权限；同号重复发布不会重复生效。已受理诊断固定其受理时的完整校准版本，不随换标变化。</p>
    <h3>校准版本</h3>
    <p class="hint">当前生效版本 v${s.calibrations?.version??0}。每次成功发布生成一个完整可追溯版本。</p>
  </section>
  <section>
    <div class="section-head"><h2>校准单台账</h2><span>${s.calibrations?.sheets?.length??0} 张 / 版本 v${s.calibrations?.version??0}</span></div>
    ${table(['校准单 / 说明','状态','生效时段（UTC）','对照点'],(s.calibrations?.sheets||[]).map(x=>[
      `<strong>${esc(x.code)}</strong><small>${esc(x.note||'')} · v${x.version||0}</small>`,
      sheetStatus(x.status),`${stamp(x.effective_from)} — ${stamp(x.effective_to)}`,
      `<small>${esc(pointsText(x.points))}</small>`]))}
    <div class="review-list" style="margin-top:18px">${(s.calibrations?.sheets||[]).map(x=>`<div class="review-choice" style="display:flex;gap:12px;align-items:center;justify-content:space-between">
      <div><strong>${esc(x.code)}</strong><small>${x.status==='draft'?'草稿可预览影响，发布后生效':'已发布 v'+x.version}</small></div>
      <div style="display:flex;gap:8px">
        <button class="outline" style="margin:0;padding:8px 12px" data-preview="${x.id}">预览影响</button>
        ${x.status==='draft'?`<button class="primary" style="padding:8px 12px" data-publish="${x.id}" ${s.user.role==='admin'?'':'disabled'}>发布</button>`:''}
      </div></div>`).join('')}</div>
    <div style="margin-top:28px">${previewPanel(selected)}</div>
  </section></div>`;
}
