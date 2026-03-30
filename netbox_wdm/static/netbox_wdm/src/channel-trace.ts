import type { TraceData, PathElement, CableSegment, CableSegmentItem } from './channel-trace-types';

declare const d3: any;

// ── Layout constants ─────────────────────────────────────────────
const NODE_WIDTH = 320;
const NODE_HEIGHT = 80;
const CABLE_ELEM_HEIGHT = 32;
const ELEM_GAP = 16;
const MARGIN = { top: 40, right: 40, bottom: 40, left: 40 };

// ── Theme helpers ────────────────────────────────────────────────
function isDarkTheme(): boolean {
  const el = document.querySelector('[data-bs-theme]');
  return el ? el.getAttribute('data-bs-theme') === 'dark' : true;
}

function colors() {
  const dark = isDarkTheme();
  return {
    bg: dark ? '#1a1a2e' : '#ffffff',
    nodeFill: dark ? '#16213e' : '#f8f9fa',
    nodeStroke: dark ? '#4a5568' : '#dee2e6',
    highlightStroke: '#3b82f6',
    text: dark ? '#e2e8f0' : '#212529',
    textMuted: dark ? '#94a3b8' : '#6c757d',
    cableLine: dark ? '#64748b' : '#adb5bd',
    portFill: dark ? '#1e293b' : '#e9ecef',
    portStroke: dark ? '#475569' : '#ced4da',
    connectedDot: '#22c55e',
    disconnectedDot: '#ef4444',
    tooltipBg: dark ? '#0f172a' : '#ffffff',
    tooltipBorder: dark ? '#334155' : '#dee2e6',
    tooltipText: dark ? '#e2e8f0' : '#212529',
    zoomBtnFill: dark ? '#1e293b' : '#f8f9fa',
    zoomBtnStroke: dark ? '#475569' : '#ced4da',
    zoomBtnText: dark ? '#e2e8f0' : '#212529',
  };
}

// ── Debug helper ─────────────────────────────────────────────────
function dbg(...args: unknown[]): void {
  if ((window as any).__WDM_DEBUG__) {
    console.log('[WDM:Trace]', ...args);
  }
}

// ── Interfaces for internal layout ──────────────────────────────
interface LayoutNode {
  element: PathElement;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface LayoutCableElem {
  item: CableSegmentItem;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface LayoutCable {
  segment: CableSegment;
  elements: LayoutCableElem[];
  lineFromY: number;
  lineToY: number;
}

interface Layout {
  nodes: LayoutNode[];
  cables: LayoutCable[];
  totalWidth: number;
  totalHeight: number;
}

// ── Compute layout positions ────────────────────────────────────
function computeLayout(data: TraceData): Layout {
  const nodes: LayoutNode[] = [];
  const cables: LayoutCable[] = [];
  let curY = MARGIN.top;
  const centerX = MARGIN.left;

  for (let i = 0; i < data.elements.length; i++) {
    const element = data.elements[i];

    // Place node
    nodes.push({
      element,
      x: centerX,
      y: curY,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    });
    curY += NODE_HEIGHT;

    // Place cable segment between this element and next
    const seg = data.cable_segments.find((s) => s.from_sequence === element.sequence);
    if (seg && seg.items.length > 0) {
      curY += ELEM_GAP;
      const lineFromY = curY;
      const elems: LayoutCableElem[] = [];

      for (const item of seg.items) {
        elems.push({
          item,
          x: centerX + (NODE_WIDTH - 200) / 2,
          y: curY,
          width: 200,
          height: CABLE_ELEM_HEIGHT,
        });
        curY += CABLE_ELEM_HEIGHT + ELEM_GAP;
      }

      const lineToY = curY - ELEM_GAP;
      cables.push({ segment: seg, elements: elems, lineFromY, lineToY });
    } else if (i < data.elements.length - 1) {
      // Gap between nodes even if no cable data
      curY += ELEM_GAP * 2;
    }
  }

  curY += MARGIN.bottom;

  return {
    nodes,
    cables,
    totalWidth: MARGIN.left + NODE_WIDTH + MARGIN.right,
    totalHeight: curY,
  };
}

// ── Tooltip helpers ──────────────────────────────────────────────
function showTooltip(tooltip: any, html: string, event: MouseEvent): void {
  const c = colors();
  tooltip
    .style('display', 'block')
    .style('background', c.tooltipBg)
    .style('border', `1px solid ${c.tooltipBorder}`)
    .style('color', c.tooltipText)
    .html(html);

  const ttNode = tooltip.node() as HTMLElement;
  const rect = ttNode.getBoundingClientRect();
  const containerRect = ttNode.parentElement!.getBoundingClientRect();

  let left = event.clientX - containerRect.left + 12;
  let top = event.clientY - containerRect.top - 12;

  if (left + rect.width > containerRect.width) {
    left = event.clientX - containerRect.left - rect.width - 12;
  }
  if (top + rect.height > containerRect.height) {
    top = containerRect.height - rect.height - 4;
  }

  tooltip.style('left', `${left}px`).style('top', `${top}px`);
}

function hideTooltip(tooltip: any): void {
  tooltip.style('display', 'none');
}

// ── Cable element color ──────────────────────────────────────────
function cableColor(item: CableSegmentItem): string {
  if (item.color) {
    return item.color.startsWith('#') ? item.color : `#${item.color}`;
  }
  return colors().cableLine;
}

// ── Render ───────────────────────────────────────────────────────
function render(container: HTMLElement, tooltipEl: HTMLElement, data: TraceData, currentChannelId: number): void {
  const layout = computeLayout(data);
  const c = colors();

  dbg('Layout computed', { nodes: layout.nodes.length, cables: layout.cables.length, totalHeight: layout.totalHeight });

  const containerRect = container.getBoundingClientRect();
  const width = containerRect.width || 800;
  const height = containerRect.height || 600;

  // Clear previous
  d3.select(container).select('svg').remove();

  const svg = d3
    .select(container)
    .append('svg')
    .attr('width', width)
    .attr('height', height)
    .style('cursor', 'grab');

  const tooltip = d3.select(tooltipEl);

  // Main group for zoom/pan
  const g = svg.append('g');

  // ── Zoom behavior ─────────────────────────────────────────
  const zoom = d3
    .zoom()
    .scaleExtent([0.2, 3])
    .on('zoom', (event: any) => {
      g.attr('transform', event.transform);
    });

  svg.call(zoom);

  // ── Draw vertical connecting lines for cable segments ─────
  for (const cable of layout.cables) {
    if (cable.elements.length === 0) continue;
    const lineX = layout.nodes[0].x + NODE_WIDTH / 2;

    g.append('line')
      .attr('x1', lineX)
      .attr('y1', cable.lineFromY)
      .attr('x2', lineX)
      .attr('y2', cable.lineToY)
      .attr('stroke', c.cableLine)
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '6,4');
  }

  // ── Draw cable elements ───────────────────────────────────
  for (const cable of layout.cables) {
    for (const le of cable.elements) {
      const group = g.append('g').attr('transform', `translate(${le.x}, ${le.y})`).style('cursor', 'pointer');

      const isCable = le.item.type === 'cable';
      const fill = isCable ? cableColor(le.item) : c.portFill;
      const stroke = isCable ? cableColor(le.item) : c.portStroke;

      group
        .append('rect')
        .attr('width', le.width)
        .attr('height', le.height)
        .attr('rx', isCable ? 4 : 3)
        .attr('fill', fill)
        .attr('fill-opacity', isCable ? 0.15 : 1)
        .attr('stroke', stroke)
        .attr('stroke-width', 1);

      // Icon prefix
      const icon = isCable ? '\u2500\u2500' : le.item.type === 'rear_port' ? '\u25c9' : '\u25cb';
      const label = `${icon}  ${le.item.name}`;

      group
        .append('text')
        .attr('x', le.width / 2)
        .attr('y', le.height / 2 + 1)
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .attr('fill', isCable ? cableColor(le.item) : c.text)
        .attr('font-size', '11px')
        .attr('font-family', 'system-ui, sans-serif')
        .text(label);

      // Tooltip
      group
        .on('mouseover', (event: MouseEvent) => {
          const lines: string[] = [`<strong>${le.item.name}</strong>`];
          if (le.item.device) lines.push(`Device: ${le.item.device}`);
          if (le.item.label) lines.push(`Label: ${le.item.label}`);
          if (le.item.status) lines.push(`Status: ${le.item.status}`);
          lines.push(`Type: ${le.item.type.replace('_', ' ')}`);
          showTooltip(tooltip, lines.join('<br>'), event);
        })
        .on('mousemove', (event: MouseEvent) => {
          const lines: string[] = [`<strong>${le.item.name}</strong>`];
          if (le.item.device) lines.push(`Device: ${le.item.device}`);
          if (le.item.label) lines.push(`Label: ${le.item.label}`);
          if (le.item.status) lines.push(`Status: ${le.item.status}`);
          lines.push(`Type: ${le.item.type.replace('_', ' ')}`);
          showTooltip(tooltip, lines.join('<br>'), event);
        })
        .on('mouseout', () => hideTooltip(tooltip))
        .on('click', () => {
          if (le.item.url) window.location.href = le.item.url;
        });
    }
  }

  // ── Draw nodes ────────────────────────────────────────────
  for (const ln of layout.nodes) {
    const isCurrent = ln.element.channel_id === currentChannelId;
    const group = g.append('g').attr('transform', `translate(${ln.x}, ${ln.y})`).style('cursor', 'pointer');

    // Node background
    group
      .append('rect')
      .attr('width', ln.width)
      .attr('height', ln.height)
      .attr('rx', 6)
      .attr('fill', c.nodeFill)
      .attr('stroke', isCurrent ? c.highlightStroke : c.nodeStroke)
      .attr('stroke-width', isCurrent ? 2.5 : 1);

    // Device name (top line)
    group
      .append('text')
      .attr('x', 12)
      .attr('y', 22)
      .attr('fill', c.text)
      .attr('font-size', '13px')
      .attr('font-weight', '600')
      .attr('font-family', 'system-ui, sans-serif')
      .text(ln.element.node_name);

    // Channel label + wavelength (middle line)
    group
      .append('text')
      .attr('x', 12)
      .attr('y', 40)
      .attr('fill', c.textMuted)
      .attr('font-size', '11px')
      .attr('font-family', 'system-ui, sans-serif')
      .text(`${ln.element.channel_label}  \u2022  ${ln.element.wavelength_nm} nm`);

    // Port info (bottom line)
    const portParts: string[] = [];
    if (ln.element.mux_port) portParts.push(`MUX: ${ln.element.mux_port.name}`);
    if (ln.element.demux_port) portParts.push(`DEMUX: ${ln.element.demux_port.name}`);
    if (portParts.length > 0) {
      group
        .append('text')
        .attr('x', 12)
        .attr('y', 56)
        .attr('fill', c.textMuted)
        .attr('font-size', '10px')
        .attr('font-family', 'system-ui, sans-serif')
        .text(portParts.join('  |  '));
    }

    // MUX connection status dot
    if (ln.element.mux_port) {
      group
        .append('circle')
        .attr('cx', ln.width - 40)
        .attr('cy', 20)
        .attr('r', 5)
        .attr('fill', ln.element.mux_connected ? c.connectedDot : c.disconnectedDot);

      group
        .append('text')
        .attr('x', ln.width - 30)
        .attr('y', 24)
        .attr('fill', c.textMuted)
        .attr('font-size', '9px')
        .attr('font-family', 'system-ui, sans-serif')
        .text('TX');
    }

    // DEMUX connection status dot
    if (ln.element.demux_port) {
      group
        .append('circle')
        .attr('cx', ln.width - 40)
        .attr('cy', 38)
        .attr('r', 5)
        .attr('fill', ln.element.demux_connected ? c.connectedDot : c.disconnectedDot);

      group
        .append('text')
        .attr('x', ln.width - 30)
        .attr('y', 42)
        .attr('fill', c.textMuted)
        .attr('font-size', '9px')
        .attr('font-family', 'system-ui, sans-serif')
        .text('RX');
    }

    // Origin badge
    if (ln.element.sequence === 0) {
      group
        .append('rect')
        .attr('x', ln.width - 72)
        .attr('y', 54)
        .attr('width', 58)
        .attr('height', 18)
        .attr('rx', 9)
        .attr('fill', c.highlightStroke)
        .attr('fill-opacity', 0.15);

      group
        .append('text')
        .attr('x', ln.width - 43)
        .attr('y', 67)
        .attr('text-anchor', 'middle')
        .attr('fill', c.highlightStroke)
        .attr('font-size', '9px')
        .attr('font-weight', '600')
        .attr('font-family', 'system-ui, sans-serif')
        .text('ORIGIN');
    }

    // Tooltip
    group
      .on('mouseover', (event: MouseEvent) => {
        const lines: string[] = [
          `<strong>${ln.element.node_name}</strong>`,
          `Channel: ${ln.element.channel_label}`,
          `Wavelength: ${ln.element.wavelength_nm} nm`,
        ];
        if (ln.element.mux_port) lines.push(`MUX: ${ln.element.mux_port.name} (${ln.element.mux_connected ? 'connected' : 'disconnected'})`);
        if (ln.element.demux_port) lines.push(`DEMUX: ${ln.element.demux_port.name} (${ln.element.demux_connected ? 'connected' : 'disconnected'})`);
        showTooltip(tooltip, lines.join('<br>'), event);
      })
      .on('mousemove', (event: MouseEvent) => {
        const lines: string[] = [
          `<strong>${ln.element.node_name}</strong>`,
          `Channel: ${ln.element.channel_label}`,
          `Wavelength: ${ln.element.wavelength_nm} nm`,
        ];
        if (ln.element.mux_port) lines.push(`MUX: ${ln.element.mux_port.name} (${ln.element.mux_connected ? 'connected' : 'disconnected'})`);
        if (ln.element.demux_port) lines.push(`DEMUX: ${ln.element.demux_port.name} (${ln.element.demux_connected ? 'connected' : 'disconnected'})`);
        showTooltip(tooltip, lines.join('<br>'), event);
      })
      .on('mouseout', () => hideTooltip(tooltip))
      .on('click', () => {
        if (ln.element.channel_url) window.location.href = ln.element.channel_url;
      });
  }

  // ── Zoom controls ─────────────────────────────────────────
  const ctrlGroup = svg.append('g').attr('transform', `translate(${width - 48}, 12)`);
  const buttons = [
    { label: '+', dy: 0, action: () => svg.transition().duration(300).call(zoom.scaleBy, 1.3) },
    { label: '\u2212', dy: 36, action: () => svg.transition().duration(300).call(zoom.scaleBy, 0.7) },
    { label: '\u21ba', dy: 72, action: () => fitView() },
  ];

  for (const btn of buttons) {
    const bg = ctrlGroup.append('g').attr('transform', `translate(0, ${btn.dy})`).style('cursor', 'pointer');

    bg.append('rect')
      .attr('width', 32)
      .attr('height', 32)
      .attr('rx', 4)
      .attr('fill', c.zoomBtnFill)
      .attr('stroke', c.zoomBtnStroke)
      .attr('stroke-width', 1);

    bg.append('text')
      .attr('x', 16)
      .attr('y', 21)
      .attr('text-anchor', 'middle')
      .attr('fill', c.zoomBtnText)
      .attr('font-size', '16px')
      .attr('font-family', 'system-ui, sans-serif')
      .text(btn.label);

    bg.on('click', (event: MouseEvent) => {
      event.stopPropagation();
      btn.action();
    });
  }

  // ── Auto-fit initial view ─────────────────────────────────
  function fitView(): void {
    const scale = Math.min(width / layout.totalWidth, height / layout.totalHeight, 1) * 0.9;
    const tx = (width - layout.totalWidth * scale) / 2;
    const ty = (height - layout.totalHeight * scale) / 2;
    const transform = d3.zoomIdentity.translate(tx, ty).scale(scale);
    svg.transition().duration(500).call(zoom.transform, transform);
  }

  fitView();
}

// ── Entry point ──────────────────────────────────────────────────
function init(): void {
  const container = document.getElementById('channel-trace-container');
  const tooltipEl = document.getElementById('channel-trace-tooltip');
  const data = (window as any).CHANNEL_TRACE_DATA as TraceData | undefined;
  const currentId = (window as any).CHANNEL_TRACE_CURRENT_ID as number | undefined;

  if (!container) {
    dbg('Container #channel-trace-container not found');
    return;
  }
  if (!tooltipEl) {
    dbg('Tooltip #channel-trace-tooltip not found');
    return;
  }
  if (!data) {
    dbg('No CHANNEL_TRACE_DATA on window');
    container.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--bs-secondary)">No trace data available.</div>';
    return;
  }
  if (!data.elements || data.elements.length === 0) {
    container.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--bs-secondary)">This channel has no elements to display.</div>';
    return;
  }

  dbg('Initializing trace visualization', { channel_id: data.channel_id, elements: data.elements.length, currentId });

  render(container, tooltipEl, data, currentId ?? data.channel_id);
}

document.addEventListener('DOMContentLoaded', init);

export { init, render };
