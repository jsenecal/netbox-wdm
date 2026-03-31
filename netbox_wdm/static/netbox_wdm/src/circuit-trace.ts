/**
 * Circuit trace — horizontal flow diagram inspired by NetBox cable trace.
 *
 * Devices as NetBox-style boxes with teal headers, flowing left-to-right.
 * Ports flush with device edges; cables fan in/out through a central badge.
 * Internal routing (PortMapping, mux→COM) shown as faint dotted lines.
 * Channel front ports shown on the client-facing side of WDM devices.
 */
import type { TraceData } from './channel-trace-types';

declare const d3: any;

// ── Constants ───────────────────────────────────────────────────
const WDM_W = 164;
const PP_W = 200;
const PORT_W = 84;
const PORT_H = 26;
const PORT_GAP = 4;
const PORT_INSET = 4;
const WDM_HEADER_H = 44;
const PP_HEADER_H = 34;
const SUBTITLE_H = 16;
const DEVICE_GAP = 150;
const MARGIN = { top: 24, right: 40, bottom: 24, left: 40 };
const FONT = 'system-ui, -apple-system, sans-serif';
const CORNER_R = 8;

// ── Theme ───────────────────────────────────────────────────────
function isDark(): boolean {
  const el = document.querySelector('[data-bs-theme]');
  return el ? el.getAttribute('data-bs-theme') === 'dark' : false;
}

function T() {
  const d = isDark();
  return {
    headerFill: d ? '#2a7070' : '#3a8a8a',
    headerText: '#fff',
    bodyFill: d ? '#1e293b' : '#fff',
    bodyStroke: d ? '#475569' : '#dee2e6',
    subtitle: d ? '#94a3b8' : '#868e96',
    portFill: d ? '#283548' : '#f0f4f8',
    portStroke: d ? '#475569' : '#ced4da',
    portText: d ? '#cbd5e1' : '#495057',
    chPortFill: d ? '#1e2d3d' : '#f4f8ff',
    chPortStroke: d ? '#3a5068' : '#b8cfe0',
    cable: d ? '#64748b' : '#adb5bd',
    badgeBg: d ? '#1e293b' : '#fff',
    badgeBorder: d ? '#475569' : '#dee2e6',
    badgeText: d ? '#94a3b8' : '#495057',
    internalLink: d ? '#475569' : '#ced4da',
    text: d ? '#e2e8f0' : '#212529',
    muted: d ? '#94a3b8' : '#6c757d',
    green: '#22c55e',
    red: '#ef4444',
    ttBg: d ? '#0f172a' : '#fff',
    ttBorder: d ? '#334155' : '#dee2e6',
    ttText: d ? '#e2e8f0' : '#212529',
    btnFill: d ? '#1e293b' : '#f8f9fa',
    btnStroke: d ? '#475569' : '#ced4da',
    btnText: d ? '#e2e8f0' : '#212529',
  };
}

// ── Data model ──────────────────────────────────────────────────
interface Port {
  id: number;
  name: string;
  url: string;
  type: string;
  side: 'left' | 'right';
  isChannel?: boolean;
}

interface InternalLink {
  fromId: number;
  toId: number;
}

interface Device {
  name: string;
  isWdm: boolean;
  ports: Port[];
  url: string;
  channels: { label: string; wl: number; muxConn: boolean; demuxConn: boolean; hasMux: boolean; hasDemux: boolean }[];
  internalLinks: InternalLink[];
}

interface Cable {
  id: number;
  name: string;
  url: string;
  color: string;
  status: string;
  portPairs: { from: number; to: number }[];
  label: string;
}

interface Graph {
  devices: Device[];
  cables: Cable[];
}

// ── Build graph from TraceData list ─────────────────────────────
function buildGraph(dataList: TraceData[]): Graph {
  const deviceMap = new Map<string, Device>();
  const deviceOrder: string[] = [];
  const portSeen = new Set<number>();
  const cableMap = new Map<number, Cable>();
  const chSeen = new Set<number>();
  const internalLinkSeen = new Set<string>();

  const sorted = [...dataList].sort(
    (a, b) => (b.cable_segments[0]?.items.length ?? 0) - (a.cable_segments[0]?.items.length ?? 0),
  );

  function ensureDev(name: string, isWdm: boolean, url: string): Device {
    if (!deviceMap.has(name)) {
      deviceMap.set(name, { name, isWdm, ports: [], url, channels: [], internalLinks: [] });
    }
    return deviceMap.get(name)!;
  }

  // Collect WDM nodes and channel front ports from elements
  for (const d of sorted) {
    for (const el of d.elements) {
      const dev = ensureDev(el.node_name, true, el.node_url);
      if (!chSeen.has(el.channel_id)) {
        chSeen.add(el.channel_id);
        dev.channels.push({
          label: el.channel_label,
          wl: el.wavelength_nm,
          muxConn: el.mux_connected,
          demuxConn: el.demux_connected,
          hasMux: !!el.mux_port,
          hasDemux: !!el.demux_port,
        });
      }
      // Add channel front ports (mux/demux) — these are client-facing
      for (const fp of [el.mux_port, el.demux_port]) {
        if (fp && !portSeen.has(fp.id)) {
          portSeen.add(fp.id);
          dev.ports.push({
            id: fp.id,
            name: fp.name,
            url: fp.url,
            type: 'front_port',
            side: 'left', // placeholder, fixed later
            isChannel: true,
          });
        }
      }
    }
  }

  // Walk cable segment items to discover device order, trunk/PP ports, and internal links
  for (const d of sorted) {
    for (const seg of d.cable_segments) {
      const items = seg.items;
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.type === 'cable') continue;
        const devName = item.device;
        if (!devName) continue;

        ensureDev(devName, false, '');
        if (!deviceOrder.includes(devName)) deviceOrder.push(devName);

        if (!portSeen.has(item.id)) {
          portSeen.add(item.id);
          const isFirstPort = items.slice(0, i).every((it) => it.type === 'cable' || it === item);
          const isLastPort = items.slice(i + 1).every((it) => it.type === 'cable' || it === item);
          const prevIsCable = i > 0 && items[i - 1].type === 'cable';

          let side: 'left' | 'right';
          if (!prevIsCable && (isFirstPort || i === 0)) side = 'right';
          else if (isLastPort) side = 'left';
          else side = prevIsCable ? 'left' : 'right';

          deviceMap.get(devName)!.ports.push({
            id: item.id,
            name: item.name,
            url: item.url,
            type: item.type,
            side,
          });
        }

        // Detect internal links: consecutive non-cable items on the same device
        if (
          i > 0 &&
          items[i - 1].type !== 'cable' &&
          items[i - 1].device === devName
        ) {
          const key = `${items[i - 1].id}-${item.id}`;
          if (!internalLinkSeen.has(key)) {
            internalLinkSeen.add(key);
            deviceMap.get(devName)!.internalLinks.push({ fromId: items[i - 1].id, toId: item.id });
          }
        }
      }

      // Extract cables with all port pairs
      for (let i = 0; i < items.length; i++) {
        if (items[i].type !== 'cable') continue;
        const cable = items[i];
        const prevPort = i > 0 && items[i - 1].type !== 'cable' ? items[i - 1] : null;
        const nextPort = i < items.length - 1 && items[i + 1].type !== 'cable' ? items[i + 1] : null;
        const pair = prevPort && nextPort ? { from: prevPort.id, to: nextPort.id } : null;

        if (cableMap.has(cable.id)) {
          if (pair) {
            const existing = cableMap.get(cable.id)!;
            if (!existing.portPairs.some((pp) => pp.from === pair.from && pp.to === pair.to)) {
              existing.portPairs.push(pair);
            }
          }
          continue;
        }
        const wl = d.wavelength_nm ?? '';
        const els = d.elements;
        const arrow =
          els.length >= 2
            ? `${els[0].node_name.replace(/.*-/, '')}\u2192${els[els.length - 1].node_name.replace(/.*-/, '')}`
            : '';
        cableMap.set(cable.id, {
          id: cable.id,
          name: cable.name,
          url: cable.url,
          color: cable.color || '',
          status: cable.status || '',
          portPairs: pair ? [pair] : [],
          label: wl ? `${wl}nm ${arrow}` : arrow,
        });
      }
    }
  }

  // Add channel→COM internal links for WDM nodes
  for (const d of sorted) {
    for (const el of d.elements) {
      const dev = deviceMap.get(el.node_name);
      if (!dev) continue;
      const rearPorts = dev.ports.filter((p) => p.type === 'rear_port' && !p.isChannel);
      const txRP = rearPorts.find((p) => /tx/i.test(p.name));
      const rxRP = rearPorts.find((p) => /rx/i.test(p.name));
      const bidiRP = rearPorts.find((p) => /com$/i.test(p.name)) || rearPorts[0];
      if (el.mux_port) {
        const target = txRP || bidiRP;
        if (target) {
          const key = `${el.mux_port.id}-${target.id}`;
          if (!internalLinkSeen.has(key)) {
            internalLinkSeen.add(key);
            dev.internalLinks.push({ fromId: el.mux_port.id, toId: target.id });
          }
        }
      }
      if (el.demux_port) {
        const target = rxRP || bidiRP;
        if (target) {
          const key = `${target.id}-${el.demux_port.id}`;
          if (!internalLinkSeen.has(key)) {
            internalLinkSeen.add(key);
            dev.internalLinks.push({ fromId: target.id, toId: el.demux_port.id });
          }
        }
      }
    }
  }

  // Ensure all WDM nodes are in the order
  for (const d of sorted) {
    for (const el of d.elements) {
      if (!deviceOrder.includes(el.node_name)) deviceOrder.push(el.node_name);
    }
  }

  const devices = deviceOrder.map((name) => deviceMap.get(name)!);
  const cables = [...cableMap.values()];

  // Fix port sides using cable segment items + device order
  const portDevIdx = new Map<number, number>();
  for (let di = 0; di < devices.length; di++) {
    for (const p of devices[di].ports) portDevIdx.set(p.id, di);
  }
  for (const d of sorted) {
    for (const seg of d.cable_segments) {
      const items = seg.items;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type !== 'cable') continue;
        const prev = i > 0 && items[i - 1].type !== 'cable' ? items[i - 1] : null;
        const next = i < items.length - 1 && items[i + 1].type !== 'cable' ? items[i + 1] : null;
        if (!prev || !next) continue;
        const pi = portDevIdx.get(prev.id);
        const ni = portDevIdx.get(next.id);
        if (pi === undefined || ni === undefined) continue;
        const pp = devices[pi].ports.find((p) => p.id === prev.id);
        const np = devices[ni].ports.find((p) => p.id === next.id);
        if (pi < ni) {
          if (pp) pp.side = 'right';
          if (np) np.side = 'left';
        } else if (pi > ni) {
          if (pp) pp.side = 'left';
          if (np) np.side = 'right';
        }
      }
    }
  }

  // Channel ports go on the opposite side from the trunk/COM ports
  for (const dev of devices) {
    if (!dev.isWdm) continue;
    const trunkSide = dev.ports.find((p) => !p.isChannel && p.type === 'rear_port')?.side;
    if (!trunkSide) continue;
    const chSide = trunkSide === 'right' ? 'left' : 'right';
    for (const p of dev.ports) {
      if (p.isChannel) p.side = chSide;
    }
  }

  return { devices, cables };
}

// ── Layout ──────────────────────────────────────────────────────
interface LPort {
  port: Port;
  relX: number;
  relY: number;
  absEdgeX: number;
  absCY: number;
}

interface LInternalLink {
  fromId: number;
  toId: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface LDevice {
  dev: Device;
  x: number;
  y: number;
  w: number;
  h: number;
  headerH: number;
  leftPorts: LPort[];
  rightPorts: LPort[];
  internalLinks: LInternalLink[];
}

interface LLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface LCable {
  cable: Cable;
  lines: LLine[];
  badgeX: number;
  badgeY: number;
}

function computeLayout(graph: Graph) {
  const portLookup = new Map<number, { absEdgeX: number; absCY: number }>();
  // Also track port center (for internal links, which connect at port center, not edge)
  const portCenter = new Map<number, { cx: number; cy: number }>();
  const lDevices: LDevice[] = [];
  let curX = MARGIN.left;

  const infos: { w: number; h: number; hH: number; lp: Port[]; rp: Port[] }[] = [];
  let maxH = 0;

  for (const dev of graph.devices) {
    const isWdm = dev.isWdm;
    const lp = dev.ports.filter((p) => p.side === 'left');
    const rp = dev.ports.filter((p) => p.side === 'right');
    const hasBothSides = lp.length > 0 && rp.length > 0;
    // Scale internal gap with number of links so bezier curves have room
    const nLinks = dev.internalLinks.length;
    const internalGap = hasBothSides ? Math.max(24, nLinks * 8, 40) : 0;
    const w = isWdm ? (hasBothSides ? Math.max(WDM_W, PORT_W * 2 + internalGap) : WDM_W) : PP_W;
    const hH = isWdm ? WDM_HEADER_H : PP_HEADER_H;
    const nPorts = Math.max(lp.length, rp.length, 1);
    const subH = isWdm && dev.channels.length ? SUBTITLE_H : 0;
    const portsH = nPorts * PORT_H + (nPorts - 1) * PORT_GAP;
    const bodyH = subH + PORT_INSET * 2 + portsH;
    const h = hH + Math.max(bodyH, 40);
    infos.push({ w, h, hH, lp, rp });
    maxH = Math.max(maxH, h);
  }

  for (let i = 0; i < graph.devices.length; i++) {
    const dev = graph.devices[i];
    const inf = infos[i];
    const y = MARGIN.top + (maxH - inf.h) / 2;
    const subH = dev.isWdm && dev.channels.length ? SUBTITLE_H : 0;
    const portsY0 = inf.hH + subH + PORT_INSET;

    const lLeft: LPort[] = [];
    let py = portsY0;
    for (const p of inf.lp) {
      const lp: LPort = {
        port: p,
        relX: 0,
        relY: py,
        absEdgeX: curX,
        absCY: y + py + PORT_H / 2,
      };
      lLeft.push(lp);
      portLookup.set(p.id, { absEdgeX: curX, absCY: lp.absCY });
      portCenter.set(p.id, { cx: curX + PORT_W, cy: lp.absCY }); // inner edge of left port
      py += PORT_H + PORT_GAP;
    }

    const lRight: LPort[] = [];
    py = portsY0;
    for (const p of inf.rp) {
      const lp: LPort = {
        port: p,
        relX: inf.w - PORT_W,
        relY: py,
        absEdgeX: curX + inf.w,
        absCY: y + py + PORT_H / 2,
      };
      lRight.push(lp);
      portLookup.set(p.id, { absEdgeX: curX + inf.w, absCY: lp.absCY });
      portCenter.set(p.id, { cx: curX + inf.w - PORT_W, cy: lp.absCY }); // inner edge of right port
      py += PORT_H + PORT_GAP;
    }

    // Resolve internal links to device-relative coordinates
    const iLinks: LInternalLink[] = [];
    for (const il of dev.internalLinks) {
      const from = portCenter.get(il.fromId);
      const to = portCenter.get(il.toId);
      if (from && to) {
        iLinks.push({
          fromId: il.fromId,
          toId: il.toId,
          x1: from.cx - curX,
          y1: from.cy - y,
          x2: to.cx - curX,
          y2: to.cy - y,
        });
      }
    }

    lDevices.push({
      dev,
      x: curX,
      y,
      w: inf.w,
      h: inf.h,
      headerH: inf.hH,
      leftPorts: lLeft,
      rightPorts: lRight,
      internalLinks: iLinks,
    });
    curX += inf.w + DEVICE_GAP;
  }

  // Cables
  const lCables: LCable[] = [];
  for (const cable of graph.cables) {
    const lines: LLine[] = [];
    for (const pp of cable.portPairs) {
      const from = portLookup.get(pp.from);
      const to = portLookup.get(pp.to);
      if (from && to) lines.push({ x1: from.absEdgeX, y1: from.absCY, x2: to.absEdgeX, y2: to.absCY });
    }
    if (!lines.length) continue;
    const avgX = lines.reduce((s, l) => s + (l.x1 + l.x2) / 2, 0) / lines.length;
    const avgY = lines.reduce((s, l) => s + (l.y1 + l.y2) / 2, 0) / lines.length;
    lCables.push({ cable, lines, badgeX: avgX, badgeY: avgY });
  }

  // Stagger cable badges in same gap
  const gapCables = new Map<string, number[]>();
  for (let ci = 0; ci < lCables.length; ci++) {
    const l0 = lCables[ci].lines[0];
    const key = `${Math.round(Math.min(l0.x1, l0.x2))}-${Math.round(Math.max(l0.x1, l0.x2))}`;
    if (!gapCables.has(key)) gapCables.set(key, []);
    gapCables.get(key)!.push(ci);
  }
  for (const indices of gapCables.values()) {
    if (indices.length <= 1) continue;
    indices.sort((a, b) => lCables[a].badgeY - lCables[b].badgeY);
    let prevY = -Infinity;
    for (const ci of indices) {
      if (lCables[ci].badgeY - prevY < 34) lCables[ci].badgeY = prevY + 34;
      prevY = lCables[ci].badgeY;
    }
  }

  const totalW = curX - DEVICE_GAP + MARGIN.right;
  const totalH = MARGIN.top + maxH + MARGIN.bottom;
  return { lDevices, lCables, totalW, totalH };
}

// ── Helpers ─────────────────────────────────────────────────────
function truncText(sel: any, maxW: number): void {
  sel.each(function (this: SVGTextElement) {
    const node = this;
    const full = node.textContent || '';
    let len = node.getComputedTextLength();
    if (len === 0 && full.length > 0) return;
    if (len <= maxW) return;
    let t = full;
    while (t.length > 1) {
      t = t.slice(0, -1);
      node.textContent = t + '\u2026';
      len = node.getComputedTextLength();
      if (len <= maxW) return;
    }
  });
}

function cableHex(color: string): string {
  if (!color) return '';
  return color.startsWith('#') ? color : `#${color}`;
}

function showTT(tt: any, html: string, ev: MouseEvent, t: ReturnType<typeof T>): void {
  tt.style('display', 'block')
    .style('background', t.ttBg)
    .style('border', `1px solid ${t.ttBorder}`)
    .style('color', t.ttText)
    .html(html);
  const tn = tt.node() as HTMLElement;
  const r = tn.getBoundingClientRect();
  const cr = tn.parentElement!.getBoundingClientRect();
  let l = ev.clientX - cr.left + 12;
  let top = ev.clientY - cr.top - 12;
  if (l + r.width > cr.width) l = ev.clientX - cr.left - r.width - 12;
  if (top + r.height > cr.height) top = cr.height - r.height - 4;
  if (top < 0) top = 4;
  tt.style('left', `${l}px`).style('top', `${top}px`);
}

function hideTT(tt: any): void {
  tt.style('display', 'none');
}

function headerPath(w: number, h: number, rx: number): string {
  return `M 0,${h} L 0,${rx} A ${rx},${rx} 0 0,1 ${rx},0 L ${w - rx},0 A ${rx},${rx} 0 0,1 ${w},${rx} L ${w},${h} Z`;
}

/** Bezier from (x1,y1) → through (bx,by) → to (x2,y2).  Lines merge at the badge center. */
function cablePathThrough(x1: number, y1: number, bx: number, by: number, x2: number, y2: number): string {
  return (
    `M ${x1},${y1} C ${x1 + (bx - x1) * 0.55},${y1} ${bx - (bx - x1) * 0.15},${by} ${bx},${by}` +
    ` C ${bx + (x2 - bx) * 0.15},${by} ${x2 - (x2 - bx) * 0.55},${y2} ${x2},${y2}`
  );
}

// ── Render ──────────────────────────────────────────────────────
function renderCircuitTrace(sel: string, ttSel: string, dataList: TraceData[]): void {
  const container = document.querySelector(sel) as HTMLElement | null;
  const ttEl = document.querySelector(ttSel) as HTMLElement | null;
  if (!container || !ttEl) return;

  const valid = dataList.filter((d) => d.elements?.length > 0);
  if (!valid.length) {
    container.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--bs-secondary)">No trace data.</div>';
    return;
  }

  const graph = buildGraph(valid);
  const layout = computeLayout(graph);
  const t = T();
  const cr = container.getBoundingClientRect();
  const W = cr.width || 1000;
  const H = cr.height || 600;

  d3.select(container).select('svg').remove();
  const svg = d3
    .select(container)
    .append('svg')
    .attr('width', W)
    .attr('height', H)
    .style('cursor', 'grab')
    .style('font-family', FONT);
  const tt = d3.select(ttEl);
  const g = svg.append('g');

  const zoom = d3
    .zoom()
    .scaleExtent([0.1, 4])
    .on('zoom', (ev: any) => g.attr('transform', ev.transform));
  svg.call(zoom);

  // ── Cables ────────────────────────────────────────────────
  for (const lc of layout.lCables) {
    const { cable, lines, badgeX, badgeY } = lc;
    const color = cableHex(cable.color) || t.cable;
    const cg = g.append('g').style('cursor', 'pointer');

    // Draw each port-pair as a path merging at the badge center
    for (const ln of lines) {
      const path = cablePathThrough(ln.x1, ln.y1, badgeX, badgeY, ln.x2, ln.y2);
      cg.append('path')
        .attr('d', path)
        .attr('fill', 'none')
        .attr('stroke', t.cable)
        .attr('stroke-width', 5)
        .attr('stroke-linecap', 'round')
        .attr('opacity', 0.1);
      cg.append('path')
        .attr('d', path)
        .attr('fill', 'none')
        .attr('stroke', color)
        .attr('stroke-width', 2)
        .attr('stroke-linecap', 'round');
      cg.append('circle').attr('cx', ln.x1).attr('cy', ln.y1).attr('r', 3).attr('fill', color);
      cg.append('circle').attr('cx', ln.x2).attr('cy', ln.y2).attr('r', 3).attr('fill', color);
    }

    // Cable badge
    const badgeG = cg.append('g');
    const hasStatus = !!cable.status;
    const nameY = hasStatus ? badgeY - 4 : badgeY;
    const nameText = badgeG
      .append('text')
      .attr('x', badgeX)
      .attr('y', nameY)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', t.badgeText)
      .attr('font-size', '9px')
      .attr('font-weight', '500')
      .text(cable.name);

    let statusLen = 0;
    if (hasStatus) {
      const statusText = badgeG
        .append('text')
        .attr('x', badgeX)
        .attr('y', badgeY + 8)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', t.muted)
        .attr('font-size', '8px')
        .text(cable.status);
      statusLen = (statusText.node() as SVGTextElement).getComputedTextLength?.() || 0;
    }

    const nameLen = (nameText.node() as SVGTextElement).getComputedTextLength?.() || cable.name.length * 5.5;
    const badgeW = Math.max(nameLen, statusLen) + 14;
    const badgeH = hasStatus ? 28 : 20;
    badgeG
      .insert('rect', ':first-child')
      .attr('x', badgeX - badgeW / 2)
      .attr('y', badgeY - badgeH / 2)
      .attr('width', badgeW)
      .attr('height', badgeH)
      .attr('rx', badgeH / 2)
      .attr('fill', t.badgeBg)
      .attr('stroke', t.badgeBorder)
      .attr('stroke-width', 0.5);

    const ttLines = [`<strong>${cable.name}</strong>`];
    if (cable.status) ttLines.push(`Status: ${cable.status}`);
    if (cable.label) ttLines.push(cable.label);
    if (cable.portPairs.length > 1) ttLines.push(`${cable.portPairs.length} fibre pairs`);
    const ttHtml = ttLines.join('<br>');
    cg.on('mouseover', (ev: MouseEvent) => showTT(tt, ttHtml, ev, t))
      .on('mousemove', (ev: MouseEvent) => showTT(tt, ttHtml, ev, t))
      .on('mouseout', () => hideTT(tt))
      .on('click', () => {
        if (cable.url) window.location.href = cable.url;
      });
  }

  // ── Devices ───────────────────────────────────────────────
  for (const ld of layout.lDevices) {
    const isWdm = ld.dev.isWdm;
    const dg = g.append('g').attr('transform', `translate(${ld.x}, ${ld.y})`);

    dg.append('rect')
      .attr('width', ld.w)
      .attr('height', ld.h)
      .attr('rx', CORNER_R)
      .attr('fill', t.bodyFill)
      .attr('stroke', t.bodyStroke)
      .attr('stroke-width', 1.5);

    dg.append('path').attr('d', headerPath(ld.w, ld.headerH, CORNER_R)).attr('fill', t.headerFill);

    dg.append('line')
      .attr('x1', 0)
      .attr('y1', ld.headerH)
      .attr('x2', ld.w)
      .attr('y2', ld.headerH)
      .attr('stroke', t.bodyStroke)
      .attr('stroke-width', 0.5);

    // Internal routing curves — subtle by default, highlighted on port hover
    const ilElements: { path: any; dot1: any; dot2: any; fromId: number; toId: number }[] = [];
    for (const il of ld.internalLinks) {
      const dx = (il.x2 - il.x1) / 3;
      const d = `M ${il.x1},${il.y1} C ${il.x1 + dx},${il.y1} ${il.x2 - dx},${il.y2} ${il.x2},${il.y2}`;
      const p = dg
        .append('path')
        .attr('d', d)
        .attr('fill', 'none')
        .attr('stroke', t.internalLink)
        .attr('stroke-width', 1)
        .attr('stroke-dasharray', '4,3')
        .attr('opacity', 0.3);
      const d1 = dg
        .append('circle')
        .attr('cx', il.x1)
        .attr('cy', il.y1)
        .attr('r', 2)
        .attr('fill', t.internalLink)
        .attr('opacity', 0.3);
      const d2 = dg
        .append('circle')
        .attr('cx', il.x2)
        .attr('cy', il.y2)
        .attr('r', 2)
        .attr('fill', t.internalLink)
        .attr('opacity', 0.3);
      ilElements.push({ path: p, dot1: d1, dot2: d2, fromId: il.fromId, toId: il.toId });
    }
    // Helper: highlight internal links connected to a port
    const hlLinks = (portId: number, on: boolean) => {
      for (const el of ilElements) {
        const match = el.fromId === portId || el.toId === portId;
        el.path
          .attr('opacity', on && match ? 0.85 : 0.3)
          .attr('stroke-width', on && match ? 2.5 : 1)
          .attr('stroke', on && match ? t.cable : t.internalLink);
        el.dot1.attr('opacity', on && match ? 0.9 : 0.3).attr('r', on && match ? 3 : 2);
        el.dot2.attr('opacity', on && match ? 0.9 : 0.3).attr('r', on && match ? 3 : 2);
      }
    };

    const nameText = dg
      .append('text')
      .attr('x', ld.w / 2)
      .attr('y', ld.headerH / 2 + 1)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('fill', t.headerText)
      .attr('font-size', isWdm ? '12px' : '11px')
      .attr('font-weight', '600')
      .text(ld.dev.name);
    truncText(nameText, ld.w - 16);

    if (isWdm && ld.dev.channels.length > 0) {
      const wls = [...new Set(ld.dev.channels.map((ch) => ch.wl))].sort((a, b) => a - b);
      const summary =
        wls.length <= 2
          ? wls.map((w) => `${w}nm`).join(', ')
          : `${ld.dev.channels.length}ch ${wls[0]}\u2013${wls[wls.length - 1]}nm`;
      const subText = dg
        .append('text')
        .attr('x', ld.w / 2)
        .attr('y', ld.headerH + SUBTITLE_H / 2 + 2)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', t.subtitle)
        .attr('font-size', '9px')
        .text(summary);
      truncText(subText, ld.w - 12);
    }

    // Ports
    const drawPort = (lp: LPort) => {
      const isCh = !!lp.port.isChannel;
      const pg = dg.append('g').attr('transform', `translate(${lp.relX}, ${lp.relY})`).style('cursor', 'pointer');

      pg.append('rect')
        .attr('width', PORT_W)
        .attr('height', PORT_H)
        .attr('rx', 3)
        .attr('fill', isCh ? t.chPortFill : t.portFill)
        .attr('stroke', isCh ? t.chPortStroke : t.portStroke)
        .attr('stroke-width', 0.5);

      const icon = lp.port.type === 'front_port' ? '\u25cb' : '\u25c9';
      const pText = pg
        .append('text')
        .attr('x', PORT_W / 2)
        .attr('y', PORT_H / 2 + 1)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', t.portText)
        .attr('font-size', '9px')
        .text(`${icon} ${lp.port.name}`);
      truncText(pText, PORT_W - 10);

      const portTT = `<strong>${lp.port.name}</strong><br>${lp.port.type.replace('_', ' ')}${isCh ? ' (channel)' : ''}<br>Device: ${ld.dev.name}`;
      pg.on('click', (ev: MouseEvent) => {
        ev.stopPropagation();
        if (lp.port.url) window.location.href = lp.port.url;
      })
        .on('mouseover', (ev: MouseEvent) => {
          ev.stopPropagation();
          showTT(tt, portTT, ev, t);
          hlLinks(lp.port.id, true);
        })
        .on('mousemove', (ev: MouseEvent) => {
          ev.stopPropagation();
          showTT(tt, portTT, ev, t);
        })
        .on('mouseout', () => {
          hideTT(tt);
          hlLinks(lp.port.id, false);
        });
    };

    for (const lp of ld.leftPorts) drawPort(lp);
    for (const lp of ld.rightPorts) drawPort(lp);

    // Header overlay
    const headerOverlay = dg
      .append('rect')
      .attr('width', ld.w)
      .attr('height', ld.headerH)
      .attr('fill', 'transparent')
      .style('cursor', 'pointer');

    const devTTLines = [`<strong>${ld.dev.name}</strong>`];
    if (ld.dev.channels.length) {
      for (const ch of ld.dev.channels) {
        let s = '';
        if (ch.hasMux) s += ch.muxConn ? ' TX\u2713' : ' TX\u2717';
        if (ch.hasDemux) s += ch.demuxConn ? ' RX\u2713' : ' RX\u2717';
        devTTLines.push(`&nbsp;&nbsp;${ch.label} (${ch.wl}nm)${s}`);
      }
    } else {
      devTTLines.push(`${ld.dev.ports.length} port(s)`);
    }
    const devTTHtml = devTTLines.join('<br>');

    headerOverlay
      .on('click', (ev: MouseEvent) => {
        ev.stopPropagation();
        if (ld.dev.url) window.location.href = ld.dev.url;
      })
      .on('mouseover', (ev: MouseEvent) => showTT(tt, devTTHtml, ev, t))
      .on('mousemove', (ev: MouseEvent) => showTT(tt, devTTHtml, ev, t))
      .on('mouseout', () => hideTT(tt));
  }

  // ── Zoom controls ─────────────────────────────────────────
  const ctrlG = svg.append('g').attr('transform', `translate(${W - 48}, 12)`);
  [
    { label: '+', dy: 0, fn: () => svg.transition().duration(300).call(zoom.scaleBy, 1.4) },
    { label: '\u2212', dy: 36, fn: () => svg.transition().duration(300).call(zoom.scaleBy, 0.7) },
    { label: '\u21ba', dy: 72, fn: () => fit() },
  ].forEach((btn) => {
    const bg = ctrlG.append('g').attr('transform', `translate(0, ${btn.dy})`).style('cursor', 'pointer');
    bg.append('rect')
      .attr('width', 32)
      .attr('height', 32)
      .attr('rx', 4)
      .attr('fill', t.btnFill)
      .attr('stroke', t.btnStroke)
      .attr('stroke-width', 1);
    bg.append('text')
      .attr('x', 16)
      .attr('y', 21)
      .attr('text-anchor', 'middle')
      .attr('fill', t.btnText)
      .attr('font-size', '16px')
      .text(btn.label);
    bg.on('click', (ev: MouseEvent) => {
      ev.stopPropagation();
      btn.fn();
    });
  });

  function fit(): void {
    const s = Math.min(W / layout.totalW, H / layout.totalH, 1) * 0.9;
    const tx = (W - layout.totalW * s) / 2;
    const ty = (H - layout.totalH * s) / 2;
    svg.transition().duration(500).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(s));
  }
  fit();
}

(window as any).renderCircuitTrace = renderCircuitTrace;
export { renderCircuitTrace };
