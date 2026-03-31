/**
 * Circuit trace — 3-tier progressive-zoom visualization.
 *
 * Overview  (scale < 0.6): Large WDM node boxes + simple colored cable lines.
 * Medium   (0.6–1.2):     Port sub-boxes on nodes, lane labels, PP name boxes.
 * Detail   (> 1.2):       Per-λ TX/RX dots, full cable boxes, PP port boxes.
 */
import type { TraceData, CableSegmentItem } from './channel-trace-types';

declare const d3: any;

// ── Zoom thresholds ─────────────────────────────────────────────
const TIER_MED = 0.6;
const TIER_DET = 1.2;

// ── Layout constants ────────────────────────────────────────────
const NODE_W = 400;
const NODE_H_OVERVIEW = 80;
const PORT_BOX_W = 90;
const PORT_BOX_H = 22;
const PORT_GAP = 6;
const PORT_PAD_X = 10;
const NODE_PAD_TOP = 44;
const NODE_PAD_BOT = 8;
const PP_W = 180;
const PP_H_MED = 32;
const PP_PAD_TOP = 20;
const CABLE_H = 22;
const CABLE_GAP = 4;
const LANE_GAP = 16;
const LANE_LABEL_H = 16;
const SECTION_GAP = 16;
const LANE_W = 170;
const MARGIN = { top: 28, right: 40, bottom: 40, left: 40 };

// ── Theme ───────────────────────────────────────────────────────
function isDark(): boolean {
  const el = document.querySelector('[data-bs-theme]');
  return el ? el.getAttribute('data-bs-theme') === 'dark' : true;
}
function C() {
  const d = isDark();
  return {
    nodeFill: d ? '#16213e' : '#f8f9fa',
    nodeStroke: d ? '#4a5568' : '#dee2e6',
    ppFill: d ? '#1a2332' : '#f0f1f3',
    ppStroke: d ? '#3a4a5c' : '#ced4da',
    text: d ? '#e2e8f0' : '#212529',
    muted: d ? '#94a3b8' : '#6c757d',
    cable: d ? '#64748b' : '#adb5bd',
    portFill: d ? '#1e293b' : '#e9ecef',
    portStroke: d ? '#475569' : '#ced4da',
    green: '#22c55e',
    red: '#ef4444',
    ttBg: d ? '#0f172a' : '#ffffff',
    ttBorder: d ? '#334155' : '#dee2e6',
    ttText: d ? '#e2e8f0' : '#212529',
    btnFill: d ? '#1e293b' : '#f8f9fa',
    btnStroke: d ? '#475569' : '#ced4da',
    btnText: d ? '#e2e8f0' : '#212529',
    laneLabel: d ? '#94a3b8' : '#6c757d',
  };
}

// ── Data model ──────────────────────────────────────────────────
interface PortRef { id: number; name: string; url: string; device: string; }
interface ChInfo { id: number; label: string; wl: number; muxName: string | null; demuxName: string | null; muxConn: boolean; demuxConn: boolean; }
interface MNode { id: number; name: string; url: string; isWdm: boolean; ports: PortRef[]; channels: ChInfo[]; }

interface LaneHop { device: string; ports: CableSegmentItem[]; cables: CableSegmentItem[]; }
interface CLane { label: string; hops: LaneHop[]; pi: number; firstCableColor: string; }
interface Section { fromId: number; toId: number; lanes: CLane[]; }

// ── Build merged graph ──────────────────────────────────────────
function buildGraph(dl: TraceData[]) {
  const nm = new Map<number, MNode>();
  const order: number[] = [];
  const chSeen = new Set<number>();
  const sorted = [...dl].sort((a, b) => b.elements.length - a.elements.length);

  for (const d of sorted) for (const el of d.elements) {
    if (!nm.has(el.node_id)) {
      nm.set(el.node_id, { id: el.node_id, name: el.node_name, url: el.node_url, isWdm: true, ports: [], channels: [] });
    }
    if (!order.includes(el.node_id)) order.push(el.node_id);
    if (!chSeen.has(el.channel_id)) {
      chSeen.add(el.channel_id);
      nm.get(el.node_id)!.channels.push({
        id: el.channel_id, label: el.channel_label, wl: el.wavelength_nm,
        muxName: el.mux_port?.name ?? null, demuxName: el.demux_port?.name ?? null,
        muxConn: el.mux_connected, demuxConn: el.demux_connected,
      });
    }
  }

  // Collect unique rear ports per WDM node (endpoints only)
  const pSeen = new Set<number>();
  for (const d of dl) for (const seg of d.cable_segments) {
    for (const item of [seg.items[0], seg.items[seg.items.length - 1]]) {
      if (item?.type === 'rear_port' && !pSeen.has(item.id)) {
        pSeen.add(item.id);
        const mn = [...nm.values()].find((n) => n.name === item.device);
        if (mn) mn.ports.push({ id: item.id, name: item.name, url: item.url, device: item.device });
      }
    }
  }

  const nodes = order.map((id) => nm.get(id)!);
  const sections: Section[] = [];

  for (let i = 0; i < nodes.length - 1; i++) {
    const fN = nodes[i], tN = nodes[i + 1];
    const lanes: CLane[] = [];
    for (let pi = 0; pi < dl.length; pi++) {
      const d = dl[pi], els = d.elements;
      for (let ei = 0; ei < els.length - 1; ei++) {
        const a = els[ei].node_id, b = els[ei + 1].node_id;
        if ((a === fN.id && b === tN.id) || (a === tN.id && b === fN.id)) {
          const seg = d.cable_segments.find((s) => s.from_sequence === els[ei].sequence);
          if (!seg || !seg.items.length) continue;
          // Decompose into per-device hops
          const hops: LaneHop[] = [];
          let curDev = '', curPorts: CableSegmentItem[] = [], curCables: CableSegmentItem[] = [];
          for (const item of seg.items) {
            if (item.type === 'cable') { curCables.push(item); }
            else {
              if (item.device !== curDev && curDev) { hops.push({ device: curDev, ports: curPorts, cables: curCables }); curPorts = []; curCables = []; }
              curDev = item.device || ''; curPorts.push(item);
            }
          }
          if (curDev) hops.push({ device: curDev, ports: curPorts, cables: curCables });

          const arrow = a === fN.id ? '\u2192' : '\u2190';
          const fS = els[ei].node_name.replace(/.*-/, ''), tS = els[ei + 1].node_name.replace(/.*-/, '');
          // Find first cable color for overview lines
          const firstCable = seg.items.find((it) => it.type === 'cable');
          const cc = firstCable?.color ? (firstCable.color.startsWith('#') ? firstCable.color : `#${firstCable.color}`) : '';

          lanes.push({ label: `${d.wavelength_nm}nm ${fS}${arrow}${tS}`, hops, pi, firstCableColor: cc });
        }
      }
    }
    if (lanes.length) sections.push({ fromId: fN.id, toId: tN.id, lanes });
  }
  return { nodes, sections };
}

// ── Layout computation ──────────────────────────────────────────
// We compute ONE layout (detail-level) and render all three tiers from it.

interface LPort { port: PortRef; rx: number; ry: number; }  // relative to node
interface LNode { n: MNode; x: number; y: number; w: number; hOver: number; hFull: number; ports: LPort[]; }
interface LCable { item: CableSegmentItem; x: number; y: number; }
interface LPP { device: string; x: number; y: number; ports: { item: CableSegmentItem; rx: number; ry: number; }[]; }
interface LLane { lane: CLane; x: number; yStart: number; cables: LCable[]; pps: LPP[]; }
interface LSection { sec: Section; lanes: LLane[]; }

function layout(nodes: MNode[], sections: Section[]) {
  const ln: LNode[] = [];
  const ls: LSection[] = [];
  let curY = MARGIN.top;
  let maxW = 0;

  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    const pc = n.ports.length;
    const portsW = pc > 0 ? pc * PORT_BOX_W + (pc - 1) * PORT_GAP + PORT_PAD_X * 2 : 0;
    const w = Math.max(NODE_W, portsW);
    const hFull = NODE_PAD_TOP + (pc > 0 ? PORT_BOX_H + NODE_PAD_BOT : NODE_PAD_BOT);

    const ports: LPort[] = [];
    if (pc > 0) {
      const totalPW = pc * PORT_BOX_W + (pc - 1) * PORT_GAP;
      let px = (w - totalPW) / 2;
      for (const p of n.ports) { ports.push({ port: p, rx: px, ry: NODE_PAD_TOP }); px += PORT_BOX_W + PORT_GAP; }
    }

    ln.push({ n, x: MARGIN.left, y: curY, w, hOver: NODE_H_OVERVIEW, hFull, ports });
    maxW = Math.max(maxW, MARGIN.left + w + MARGIN.right);
    curY += hFull;

    const sec = sections.find((s) => s.fromId === n.id);
    if (sec) {
      curY += SECTION_GAP;
      const lc = sec.lanes.length;
      const totalLW = lc * LANE_W + (lc - 1) * LANE_GAP;
      let secMaxH = 0;

      const lLanes: LLane[] = [];
      for (let li = 0; li < lc; li++) {
        const lane = sec.lanes[li];
        const lx = MARGIN.left + li * (LANE_W + LANE_GAP);
        let ly = curY + LANE_LABEL_H;
        const cables: LCable[] = [];
        const pps: LPP[] = [];

        for (let hi = 0; hi < lane.hops.length; hi++) {
          const hop = lane.hops[hi];
          const isEnd = hi === 0 || hi === lane.hops.length - 1;

          if (!isEnd) {
            // PP box
            const ppPorts: LPP['ports'] = [];
            const ppW = LANE_W;
            let ppx = 4;
            for (const p of hop.ports) {
              ppPorts.push({ item: p, rx: ppx, ry: PP_PAD_TOP });
              ppx += 62 + 4;
            }
            const ppH = PP_PAD_TOP + (hop.ports.length > 0 ? PORT_BOX_H - 2 + 4 : 4);
            pps.push({ device: hop.device, x: lx, y: ly, ports: ppPorts });
            ly += ppH + CABLE_GAP;
          }
          for (const c of hop.cables) { cables.push({ item: c, x: lx, y: ly }); ly += CABLE_H + CABLE_GAP; }
        }
        secMaxH = Math.max(secMaxH, ly - curY);
        lLanes.push({ lane, x: lx, yStart: curY, cables, pps });
      }
      ls.push({ sec, lanes: lLanes });
      maxW = Math.max(maxW, MARGIN.left + totalLW + MARGIN.right);
      curY += secMaxH + SECTION_GAP;
    }
  }
  curY += MARGIN.bottom;
  return { ln, ls, tw: maxW, th: curY };
}

// ── Tooltip ─────────────────────────────────────────────────────
function showTT(tt: any, html: string, ev: MouseEvent, c: ReturnType<typeof C>): void {
  tt.style('display', 'block').style('background', c.ttBg).style('border', `1px solid ${c.ttBorder}`).style('color', c.ttText).html(html);
  const tn = tt.node() as HTMLElement, r = tn.getBoundingClientRect(), cr = tn.parentElement!.getBoundingClientRect();
  let l = ev.clientX - cr.left + 12, t = ev.clientY - cr.top - 12;
  if (l + r.width > cr.width) l = ev.clientX - cr.left - r.width - 12;
  if (t + r.height > cr.height) t = cr.height - r.height - 4;
  tt.style('left', `${l}px`).style('top', `${t}px`);
}
function hideTT(tt: any): void { tt.style('display', 'none'); }
function cc(item: CableSegmentItem): string { return item.color ? (item.color.startsWith('#') ? item.color : `#${item.color}`) : C().cable; }

// ── RENDER ──────────────────────────────────────────────────────
function renderCircuitTrace(sel: string, ttSel: string, dataList: TraceData[]): void {
  const container = document.querySelector(sel) as HTMLElement | null;
  const ttEl = document.querySelector(ttSel) as HTMLElement | null;
  if (!container || !ttEl) return;
  const valid = dataList.filter((d) => d.elements?.length > 0);
  if (!valid.length) { container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--bs-secondary)">No trace data.</div>'; return; }

  const { nodes, sections } = buildGraph(valid);
  const L = layout(nodes, sections);
  const c = C();
  const cr = container.getBoundingClientRect();
  const W = cr.width || 900, H = cr.height || 700;

  d3.select(container).select('svg').remove();
  const svg = d3.select(container).append('svg').attr('width', W).attr('height', H).style('cursor', 'grab');
  const tt = d3.select(ttEl);
  const g = svg.append('g');

  // Three tier groups
  const gOver = g.append('g').attr('class', 'tier-overview');
  const gMed = g.append('g').attr('class', 'tier-medium').attr('display', 'none');
  const gDet = g.append('g').attr('class', 'tier-detail').attr('display', 'none');

  const zoom = d3.zoom().scaleExtent([0.08, 4]).on('zoom', (ev: any) => {
    g.attr('transform', ev.transform);
    const k = ev.transform.k;
    gOver.attr('display', k < TIER_MED ? null : 'none');
    gMed.attr('display', k >= TIER_MED && k < TIER_DET ? null : 'none');
    gDet.attr('display', k >= TIER_DET ? null : 'none');
  });
  svg.call(zoom);

  // ═══════════════════════════════════════════════════════════
  // TIER 1: OVERVIEW
  // ═══════════════════════════════════════════════════════════
  for (const ln of L.ln) {
    const ng = gOver.append('g').attr('transform', `translate(${ln.x}, ${ln.y})`);
    ng.append('rect').attr('width', ln.w).attr('height', ln.hOver).attr('rx', 8)
      .attr('fill', c.nodeFill).attr('stroke', c.nodeStroke).attr('stroke-width', 1.5);
    ng.append('text').attr('x', 16).attr('y', 30).attr('fill', c.text)
      .attr('font-size', '16px').attr('font-weight', '700').attr('font-family', 'system-ui, sans-serif').text(ln.n.name);
    // Channel summary
    const wls = [...new Set(ln.n.channels.map((ch) => ch.wl))].sort((a, b) => a - b);
    const summary = wls.length <= 1 ? (wls[0] ? `${wls[0]}nm` : '') :
      `${ln.n.channels.length}ch  ${wls[0]}\u2013${wls[wls.length - 1]}nm`;
    ng.append('text').attr('x', 16).attr('y', 52).attr('fill', c.muted)
      .attr('font-size', '13px').attr('font-family', 'system-ui, sans-serif').text(summary);
    ng.style('cursor', 'pointer').on('click', () => { if (ln.n.url) window.location.href = ln.n.url; });
  }
  // Overview cable lines
  for (const ls of L.ls) {
    const fromLn = L.ln.find((n) => n.n.id === ls.sec.fromId)!;
    const toLn = L.ln.find((n) => n.n.id === ls.sec.toId)!;
    const y1 = fromLn.y + fromLn.hOver;
    const y2 = toLn.y;
    const lc = ls.sec.lanes.length;
    const totalW = lc * 6 + (lc - 1) * 4;
    const startX = fromLn.x + fromLn.w / 2 - totalW / 2;
    for (let li = 0; li < lc; li++) {
      const lx = startX + li * 10 + 3;
      const lineColor = ls.sec.lanes[li].firstCableColor || c.cable;
      gOver.append('line').attr('x1', lx).attr('y1', y1).attr('x2', lx).attr('y2', y2)
        .attr('stroke', lineColor).attr('stroke-width', 4).attr('stroke-linecap', 'round').attr('opacity', 0.7);
    }
  }

  // ═══════════════════════════════════════════════════════════
  // TIER 2: MEDIUM
  // ═══════════════════════════════════════════════════════════
  for (const ln of L.ln) {
    const ng = gMed.append('g').attr('transform', `translate(${ln.x}, ${ln.y})`);
    ng.append('rect').attr('width', ln.w).attr('height', ln.hFull).attr('rx', 6)
      .attr('fill', c.nodeFill).attr('stroke', c.nodeStroke).attr('stroke-width', 1);
    ng.append('text').attr('x', 12).attr('y', 22).attr('fill', c.text)
      .attr('font-size', '14px').attr('font-weight', '600').attr('font-family', 'system-ui, sans-serif').text(ln.n.name)
      .style('cursor', 'pointer').on('click', () => { if (ln.n.url) window.location.href = ln.n.url; });
    // Ports
    for (const p of ln.ports) {
      const pg = ng.append('g').attr('transform', `translate(${p.rx}, ${p.ry})`).style('cursor', 'pointer');
      pg.append('rect').attr('width', PORT_BOX_W).attr('height', PORT_BOX_H).attr('rx', 3)
        .attr('fill', c.portFill).attr('stroke', c.portStroke).attr('stroke-width', 1);
      pg.append('text').attr('x', PORT_BOX_W / 2).attr('y', PORT_BOX_H / 2 + 1)
        .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle').attr('fill', c.text)
        .attr('font-size', '10px').attr('font-family', 'system-ui, sans-serif').text(p.port.name);
      pg.on('click', () => { if (p.port.url) window.location.href = p.port.url; });
    }
  }
  // Medium lanes: labels + cable lines + PP name boxes
  for (const ls of L.ls) {
    for (const ll of ls.lanes) {
      // Label
      gMed.append('text').attr('x', ll.x + LANE_W / 2).attr('y', ll.yStart + LANE_LABEL_H - 3)
        .attr('text-anchor', 'middle').attr('fill', c.laneLabel)
        .attr('font-size', '9px').attr('font-weight', '600').attr('font-family', 'system-ui, sans-serif')
        .text(ll.lane.label);
      // PP name-only boxes
      for (const pp of ll.pps) {
        const pg = gMed.append('g').attr('transform', `translate(${pp.x}, ${pp.y})`);
        pg.append('rect').attr('width', LANE_W).attr('height', PP_H_MED).attr('rx', 3)
          .attr('fill', c.ppFill).attr('stroke', c.ppStroke).attr('stroke-width', 1).attr('stroke-dasharray', '4,2');
        pg.append('text').attr('x', LANE_W / 2).attr('y', PP_H_MED / 2 + 1)
          .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle').attr('fill', c.muted)
          .attr('font-size', '10px').attr('font-weight', '500').attr('font-family', 'system-ui, sans-serif')
          .text(pp.device);
      }
      // Cable name lines
      for (const cb of ll.cables) {
        const cg = gMed.append('g').attr('transform', `translate(${cb.x}, ${cb.y})`);
        cg.append('rect').attr('width', LANE_W).attr('height', CABLE_H).attr('rx', 3)
          .attr('fill', cc(cb.item)).attr('fill-opacity', 0.1).attr('stroke', cc(cb.item)).attr('stroke-width', 1);
        cg.append('text').attr('x', LANE_W / 2).attr('y', CABLE_H / 2 + 1)
          .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle').attr('fill', cc(cb.item))
          .attr('font-size', '9px').attr('font-family', 'system-ui, sans-serif')
          .text(cb.item.name);
      }
    }
  }

  // ═══════════════════════════════════════════════════════════
  // TIER 3: DETAIL
  // ═══════════════════════════════════════════════════════════
  for (const ln of L.ln) {
    const ng = gDet.append('g').attr('transform', `translate(${ln.x}, ${ln.y})`);
    ng.append('rect').attr('width', ln.w).attr('height', ln.hFull).attr('rx', 6)
      .attr('fill', c.nodeFill).attr('stroke', c.nodeStroke).attr('stroke-width', 1);
    ng.append('text').attr('x', 12).attr('y', 22).attr('fill', c.text)
      .attr('font-size', '14px').attr('font-weight', '600').attr('font-family', 'system-ui, sans-serif').text(ln.n.name)
      .style('cursor', 'pointer').on('click', () => { if (ln.n.url) window.location.href = ln.n.url; });

    // Per-wavelength TX/RX dots
    if (ln.n.channels.length > 0) {
      const sorted = [...ln.n.channels].sort((a, b) => a.wl - b.wl);
      const dotSp = 14;
      const maxDots = Math.min(sorted.length, Math.floor((ln.w - 120) / dotSp));
      const shown = sorted.slice(0, maxDots);
      let dx = ln.w - 12 - (shown.length - 1) * dotSp;
      ng.append('text').attr('x', dx - 16).attr('y', 12).attr('fill', c.muted)
        .attr('font-size', '7px').attr('font-family', 'system-ui, sans-serif').text('TX');
      ng.append('text').attr('x', dx - 16).attr('y', 24).attr('fill', c.muted)
        .attr('font-size', '7px').attr('font-family', 'system-ui, sans-serif').text('RX');
      for (let ci = 0; ci < shown.length; ci++) {
        const ch = shown[ci], cx = dx + ci * dotSp;
        if (ch.muxName) ng.append('circle').attr('cx', cx).attr('cy', 10).attr('r', 3).attr('fill', ch.muxConn ? c.green : c.red);
        if (ch.demuxName) ng.append('circle').attr('cx', cx).attr('cy', 22).attr('r', 3).attr('fill', ch.demuxConn ? c.green : c.red);
      }
      if (sorted.length > maxDots) {
        ng.append('text').attr('x', ln.w - 4).attr('y', 16).attr('text-anchor', 'end')
          .attr('fill', c.muted).attr('font-size', '8px').attr('font-family', 'system-ui, sans-serif')
          .text(`+${sorted.length - maxDots}`);
      }
    }

    // Ports
    for (const p of ln.ports) {
      const pg = ng.append('g').attr('transform', `translate(${p.rx}, ${p.ry})`).style('cursor', 'pointer');
      pg.append('rect').attr('width', PORT_BOX_W).attr('height', PORT_BOX_H).attr('rx', 3)
        .attr('fill', c.portFill).attr('stroke', c.portStroke).attr('stroke-width', 1);
      pg.append('text').attr('x', PORT_BOX_W / 2).attr('y', PORT_BOX_H / 2 + 1)
        .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle').attr('fill', c.text)
        .attr('font-size', '10px').attr('font-family', 'system-ui, sans-serif').text(p.port.name);
      pg.on('click', () => { if (p.port.url) window.location.href = p.port.url; })
        .on('mouseover', (ev: MouseEvent) => showTT(tt, `<strong>${p.port.name}</strong><br>Device: ${p.port.device}`, ev, c))
        .on('mousemove', (ev: MouseEvent) => showTT(tt, `<strong>${p.port.name}</strong><br>Device: ${p.port.device}`, ev, c))
        .on('mouseout', () => hideTT(tt));
    }

    // Node tooltip
    const ntt = (ev: MouseEvent) => {
      const lines = [`<strong>${ln.n.name}</strong>`];
      for (const ch of ln.n.channels) {
        let s = ''; if (ch.muxName) s += ch.muxConn ? ' TX\u2713' : ' TX\u2717'; if (ch.demuxName) s += ch.demuxConn ? ' RX\u2713' : ' RX\u2717';
        lines.push(`&nbsp;&nbsp;${ch.label} (${ch.wl}nm)${s}`);
      }
      showTT(tt, lines.join('<br>'), ev, c);
    };
    ng.on('mouseover', ntt).on('mousemove', ntt).on('mouseout', () => hideTT(tt));
  }

  // Detail lanes: full cable boxes + PP with port boxes
  for (const ls of L.ls) {
    for (const ll of ls.lanes) {
      gDet.append('text').attr('x', ll.x + LANE_W / 2).attr('y', ll.yStart + LANE_LABEL_H - 3)
        .attr('text-anchor', 'middle').attr('fill', c.laneLabel)
        .attr('font-size', '9px').attr('font-weight', '600').attr('font-family', 'system-ui, sans-serif')
        .text(ll.lane.label);

      // PP detail boxes with ports
      for (const pp of ll.pps) {
        const ppH = PP_PAD_TOP + (pp.ports.length > 0 ? PORT_BOX_H - 2 + 4 : 4);
        const pg = gDet.append('g').attr('transform', `translate(${pp.x}, ${pp.y})`);
        pg.append('rect').attr('width', LANE_W).attr('height', ppH).attr('rx', 3)
          .attr('fill', c.ppFill).attr('stroke', c.ppStroke).attr('stroke-width', 1).attr('stroke-dasharray', '4,2');
        pg.append('text').attr('x', 8).attr('y', 14).attr('fill', c.muted)
          .attr('font-size', '10px').attr('font-weight', '500').attr('font-family', 'system-ui, sans-serif').text(pp.device);
        for (const p of pp.ports) {
          const ppg = pg.append('g').attr('transform', `translate(${p.rx}, ${p.ry})`).style('cursor', 'pointer');
          const isFP = p.item.type === 'front_port';
          ppg.append('rect').attr('width', 60).attr('height', PORT_BOX_H - 2).attr('rx', 2)
            .attr('fill', c.portFill).attr('stroke', c.portStroke).attr('stroke-width', 0.5);
          ppg.append('text').attr('x', 30).attr('y', (PORT_BOX_H - 2) / 2 + 1)
            .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle').attr('fill', c.muted)
            .attr('font-size', '8px').attr('font-family', 'system-ui, sans-serif')
            .text(`${isFP ? '\u25cb' : '\u25c9'} ${p.item.name}`);
          ppg.on('click', () => { if (p.item.url) window.location.href = p.item.url; })
            .on('mouseover', (ev: MouseEvent) => showTT(tt, `<strong>${p.item.name}</strong><br>Device: ${p.item.device}<br>Type: ${p.item.type.replace('_', ' ')}`, ev, c))
            .on('mousemove', (ev: MouseEvent) => showTT(tt, `<strong>${p.item.name}</strong><br>Device: ${p.item.device}<br>Type: ${p.item.type.replace('_', ' ')}`, ev, c))
            .on('mouseout', () => hideTT(tt));
        }
      }

      // Cable boxes
      for (const cb of ll.cables) {
        const cg = gDet.append('g').attr('transform', `translate(${cb.x}, ${cb.y})`).style('cursor', 'pointer');
        cg.append('rect').attr('width', LANE_W).attr('height', CABLE_H).attr('rx', 3)
          .attr('fill', cc(cb.item)).attr('fill-opacity', 0.12).attr('stroke', cc(cb.item)).attr('stroke-width', 1);
        cg.append('text').attr('x', LANE_W / 2).attr('y', CABLE_H / 2 + 1)
          .attr('text-anchor', 'middle').attr('dominant-baseline', 'middle').attr('fill', cc(cb.item))
          .attr('font-size', '9px').attr('font-family', 'system-ui, sans-serif')
          .text(`\u2500\u2500  ${cb.item.name}`);
        cg.on('mouseover', (ev: MouseEvent) => { const l = [`<strong>${cb.item.name}</strong>`]; if (cb.item.status) l.push(`Status: ${cb.item.status}`); showTT(tt, l.join('<br>'), ev, c); })
          .on('mousemove', (ev: MouseEvent) => { const l = [`<strong>${cb.item.name}</strong>`]; if (cb.item.status) l.push(`Status: ${cb.item.status}`); showTT(tt, l.join('<br>'), ev, c); })
          .on('mouseout', () => hideTT(tt))
          .on('click', () => { if (cb.item.url) window.location.href = cb.item.url; });
      }
    }
  }

  // ── Zoom controls ─────────────────────────────────────────
  const cg = svg.append('g').attr('transform', `translate(${W - 48}, 12)`);
  [
    { label: '+', dy: 0, fn: () => svg.transition().duration(300).call(zoom.scaleBy, 1.4) },
    { label: '\u2212', dy: 36, fn: () => svg.transition().duration(300).call(zoom.scaleBy, 0.7) },
    { label: '\u21ba', dy: 72, fn: () => fit() },
  ].forEach((btn) => {
    const bg = cg.append('g').attr('transform', `translate(0, ${btn.dy})`).style('cursor', 'pointer');
    bg.append('rect').attr('width', 32).attr('height', 32).attr('rx', 4)
      .attr('fill', c.btnFill).attr('stroke', c.btnStroke).attr('stroke-width', 1);
    bg.append('text').attr('x', 16).attr('y', 21).attr('text-anchor', 'middle')
      .attr('fill', c.btnText).attr('font-size', '16px').attr('font-family', 'system-ui, sans-serif').text(btn.label);
    bg.on('click', (ev: MouseEvent) => { ev.stopPropagation(); btn.fn(); });
  });

  function fit(): void {
    const s = Math.min(W / L.tw, H / L.th, 1) * 0.9;
    const tx = (W - L.tw * s) / 2, ty = (H - L.th * s) / 2;
    svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(s));
  }
  fit();
}

(window as any).renderCircuitTrace = renderCircuitTrace;
export { renderCircuitTrace };
