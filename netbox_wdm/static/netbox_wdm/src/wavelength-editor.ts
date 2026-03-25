import type { ChannelData, EditorConfig, PortData } from './wavelength-editor-types';

interface PortMapping {
  mux: number | null;
  demux: number | null;
}

interface Change {
  channelId: number;
  oldMux: number | null;
  newMux: number | null;
  oldDemux: number | null;
  newDemux: number | null;
}

function getCsrfToken(): string {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

function clearElement(el: HTMLElement): void {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

class WavelengthEditor {
  private config: EditorConfig;
  private container: HTMLElement;
  private currentMapping: Map<number, PortMapping>;
  private initialMapping: Map<number, PortMapping>;
  private undoStack: Change[] = [];
  private redoStack: Change[] = [];
  private lastUpdated: string;
  private isDuplex: boolean;

  private undoBtn!: HTMLButtonElement;
  private redoBtn!: HTMLButtonElement;
  private saveBtn!: HTMLButtonElement;
  private dirtyBadge!: HTMLSpanElement;
  private messageArea!: HTMLDivElement;

  constructor(container: HTMLElement, config: EditorConfig) {
    this.container = container;
    this.config = config;
    this.lastUpdated = config.lastUpdated;
    this.isDuplex = config.fiberType === 'duplex';

    this.currentMapping = new Map();
    this.initialMapping = new Map();
    for (const ch of config.channels) {
      const mapping: PortMapping = {
        mux: ch.mux_front_port_id,
        demux: ch.demux_front_port_id,
      };
      this.currentMapping.set(ch.id, { ...mapping });
      this.initialMapping.set(ch.id, { ...mapping });
    }

    this.render();
    this.bindKeyboard();
    this.bindBeforeUnload();
  }

  private render(): void {
    clearElement(this.container);

    this.messageArea = document.createElement('div');
    this.container.appendChild(this.messageArea);

    const toolbar = document.createElement('div');
    toolbar.className = 'd-flex align-items-center gap-2 mb-3';

    this.undoBtn = this.makeButton('mdi mdi-undo', 'Undo', () => this.undo());
    this.redoBtn = this.makeButton('mdi mdi-redo', 'Redo', () => this.redo());
    this.saveBtn = this.makeButton('mdi mdi-content-save', 'Save', () => this.save());
    this.saveBtn.classList.replace('btn-outline-secondary', 'btn-primary');

    this.dirtyBadge = document.createElement('span');
    this.dirtyBadge.className = 'badge bg-warning text-dark ms-2 d-none';
    this.dirtyBadge.textContent = 'Unsaved changes';

    toolbar.appendChild(this.undoBtn);
    toolbar.appendChild(this.redoBtn);
    toolbar.appendChild(this.saveBtn);
    toolbar.appendChild(this.dirtyBadge);
    this.container.appendChild(toolbar);

    const table = document.createElement('table');
    table.className = 'table table-sm table-hover';

    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    const headers = this.isDuplex
      ? ['Grid Pos', 'Label', 'Wavelength (nm)', 'MUX Port', 'DEMUX Port', 'Status']
      : ['Grid Pos', 'Label', 'Wavelength (nm)', 'Port', 'Status'];
    for (const h of headers) {
      const th = document.createElement('th');
      th.scope = 'col';
      th.textContent = h;
      headerRow.appendChild(th);
    }
    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    const sorted = [...this.config.channels].sort((a, b) => a.grid_position - b.grid_position);
    for (const ch of sorted) {
      const tr = document.createElement('tr');
      tr.dataset.channelId = String(ch.id);

      this.addCell(tr, String(ch.grid_position));
      this.addCell(tr, ch.label);
      this.addCell(tr, String(ch.wavelength_nm));

      // MUX port column (always shown)
      const muxTd = document.createElement('td');
      if (ch.status === 'available') {
        const select = this.buildPortSelect(ch, 'mux');
        muxTd.appendChild(select);
      } else {
        const span = document.createElement('span');
        const lockIcon = document.createElement('i');
        lockIcon.className = 'mdi mdi-lock me-1';
        if (ch.service_name) {
          lockIcon.title = ch.service_name;
        }
        span.appendChild(lockIcon);
        span.appendChild(document.createTextNode(ch.mux_front_port_name || 'Unassigned'));
        muxTd.appendChild(span);
      }
      tr.appendChild(muxTd);

      // DEMUX port column (duplex only)
      if (this.isDuplex) {
        const demuxTd = document.createElement('td');
        if (ch.status === 'available') {
          const select = this.buildPortSelect(ch, 'demux');
          demuxTd.appendChild(select);
        } else {
          const span = document.createElement('span');
          const lockIcon = document.createElement('i');
          lockIcon.className = 'mdi mdi-lock me-1';
          if (ch.service_name) {
            lockIcon.title = ch.service_name;
          }
          span.appendChild(lockIcon);
          span.appendChild(document.createTextNode(ch.demux_front_port_name || 'Unassigned'));
          demuxTd.appendChild(span);
        }
        tr.appendChild(demuxTd);
      }

      const statusTd = document.createElement('td');
      const badge = document.createElement('span');
      if (ch.status === 'lit') {
        badge.className = 'wdm-badge wdm-badge--lit';
        badge.textContent = 'Lit';
      } else if (ch.status === 'reserved') {
        badge.className = 'wdm-badge wdm-badge--reserved';
        badge.textContent = 'Reserved';
      } else {
        badge.className = 'wdm-badge wdm-badge--available';
        badge.textContent = 'Available';
      }
      statusTd.appendChild(badge);
      tr.appendChild(statusTd);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    this.container.appendChild(table);

    this.updateToolbar();
  }

  private addCell(tr: HTMLTableRowElement, text: string): void {
    const td = document.createElement('td');
    td.textContent = text;
    tr.appendChild(td);
  }

  private getAssignedPortIds(): Set<number> {
    const assigned = new Set<number>();
    for (const ch of this.config.channels) {
      const mapping = this.currentMapping.get(ch.id);
      if (mapping) {
        if (mapping.mux) assigned.add(mapping.mux);
        if (mapping.demux) assigned.add(mapping.demux);
      }
    }
    return assigned;
  }

  private buildPortSelect(ch: ChannelData, role: 'mux' | 'demux'): HTMLSelectElement {
    const select = document.createElement('select');
    select.className = 'form-select form-select-sm';
    select.dataset.channelId = String(ch.id);
    select.dataset.portRole = role;

    const unassigned = document.createElement('option');
    unassigned.value = '';
    unassigned.textContent = '-- Unassigned --';
    select.appendChild(unassigned);

    const currentMapping = this.currentMapping.get(ch.id);
    const currentPortId = currentMapping ? currentMapping[role] : null;
    const availableIds = new Set(this.config.availablePorts.map((p) => p.id));

    // Include the currently assigned port if it's not in available ports
    const origPortId = role === 'mux' ? ch.mux_front_port_id : ch.demux_front_port_id;
    const origPortName = role === 'mux' ? ch.mux_front_port_name : ch.demux_front_port_name;
    if (origPortId && !availableIds.has(origPortId)) {
      const opt = document.createElement('option');
      opt.value = String(origPortId);
      opt.textContent = origPortName || `Port ${origPortId}`;
      select.appendChild(opt);
    }

    // Collect ports assigned to other available channels that aren't in available pool
    const otherAssigned = new Map<number, string>();
    for (const other of this.config.channels) {
      if (other.id !== ch.id && other.status === 'available') {
        const otherPortId = role === 'mux' ? other.mux_front_port_id : other.demux_front_port_id;
        const otherPortName = role === 'mux' ? other.mux_front_port_name : other.demux_front_port_name;
        if (otherPortId && !availableIds.has(otherPortId)) {
          otherAssigned.set(otherPortId, otherPortName || `Port ${otherPortId}`);
        }
      }
    }

    for (const port of this.config.availablePorts) {
      const opt = document.createElement('option');
      opt.value = String(port.id);
      opt.textContent = port.name;
      select.appendChild(opt);
    }

    for (const [portId, portName] of otherAssigned) {
      const opt = document.createElement('option');
      opt.value = String(portId);
      opt.textContent = portName;
      select.appendChild(opt);
    }

    select.value = currentPortId ? String(currentPortId) : '';

    select.addEventListener('change', () => {
      const newPortId = select.value ? Number(select.value) : null;
      const mapping = this.currentMapping.get(ch.id);
      if (!mapping) return;
      const oldMux = mapping.mux;
      const oldDemux = mapping.demux;

      if (role === 'mux') {
        if (newPortId === oldMux) return;
        mapping.mux = newPortId;
        this.undoStack.push({
          channelId: ch.id,
          oldMux,
          newMux: newPortId,
          oldDemux: oldDemux,
          newDemux: oldDemux,
        });
      } else {
        if (newPortId === oldDemux) return;
        mapping.demux = newPortId;
        this.undoStack.push({
          channelId: ch.id,
          oldMux: oldMux,
          newMux: oldMux,
          oldDemux,
          newDemux: newPortId,
        });
      }
      this.redoStack = [];
      this.updateToolbar();
    });

    return select;
  }

  private makeButton(iconClass: string, label: string, onClick: () => void): HTMLButtonElement {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-sm btn-outline-secondary';
    btn.title = label;
    const icon = document.createElement('i');
    icon.className = iconClass;
    btn.appendChild(icon);
    btn.appendChild(document.createTextNode(' ' + label));
    btn.addEventListener('click', onClick);
    return btn;
  }

  private isDirty(): boolean {
    for (const [chId, mapping] of this.currentMapping) {
      const initial = this.initialMapping.get(chId);
      if (!initial) return true;
      if (initial.mux !== mapping.mux || initial.demux !== mapping.demux) return true;
    }
    return false;
  }

  private updateToolbar(): void {
    this.undoBtn.disabled = this.undoStack.length === 0;
    this.redoBtn.disabled = this.redoStack.length === 0;
    const dirty = this.isDirty();
    this.saveBtn.disabled = !dirty;
    if (dirty) {
      this.dirtyBadge.classList.remove('d-none');
    } else {
      this.dirtyBadge.classList.add('d-none');
    }
  }

  private undo(): void {
    const change = this.undoStack.pop();
    if (!change) return;
    const mapping = this.currentMapping.get(change.channelId);
    if (mapping) {
      mapping.mux = change.oldMux;
      mapping.demux = change.oldDemux;
    }
    this.redoStack.push(change);
    this.syncSelect(change.channelId, 'mux');
    if (this.isDuplex) {
      this.syncSelect(change.channelId, 'demux');
    }
    this.updateToolbar();
  }

  private redo(): void {
    const change = this.redoStack.pop();
    if (!change) return;
    const mapping = this.currentMapping.get(change.channelId);
    if (mapping) {
      mapping.mux = change.newMux;
      mapping.demux = change.newDemux;
    }
    this.undoStack.push(change);
    this.syncSelect(change.channelId, 'mux');
    if (this.isDuplex) {
      this.syncSelect(change.channelId, 'demux');
    }
    this.updateToolbar();
  }

  private syncSelect(channelId: number, role: 'mux' | 'demux'): void {
    const select = this.container.querySelector(
      `select[data-channel-id="${channelId}"][data-port-role="${role}"]`,
    ) as HTMLSelectElement | null;
    if (select) {
      const mapping = this.currentMapping.get(channelId);
      const val = mapping ? mapping[role] : null;
      select.value = val ? String(val) : '';
    }
  }

  private async save(): Promise<void> {
    this.saveBtn.disabled = true;
    clearElement(this.saveBtn);
    this.saveBtn.textContent = 'Saving...';

    const mapping: Record<string, { mux: number | null; demux: number | null }> = {};
    for (const [chId, portMapping] of this.currentMapping) {
      mapping[String(chId)] = { mux: portMapping.mux, demux: portMapping.demux };
    }

    try {
      const resp = await fetch(this.config.applyUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken(),
        },
        body: JSON.stringify({
          mapping,
          last_updated: this.lastUpdated,
        }),
      });

      if (resp.status === 200) {
        const data = (await resp.json()) as {
          added: number;
          removed: number;
          changed: number;
          last_updated?: string;
        };
        if (data.last_updated) {
          this.lastUpdated = data.last_updated;
        }
        for (const [chId, portMapping] of this.currentMapping) {
          this.initialMapping.set(chId, { ...portMapping });
        }
        this.undoStack = [];
        this.redoStack = [];
        this.showMessage(
          'success',
          `Saved: ${data.added} added, ${data.removed} removed, ${data.changed} changed.`,
        );
      } else if (resp.status === 409) {
        this.showConflict();
      } else {
        const data = (await resp.json()) as { errors?: string[] };
        const msg = data.errors ? data.errors.join(', ') : 'Validation error';
        this.showMessage('danger', msg);
      }
    } catch (err) {
      this.showMessage('danger', 'Network error: ' + (err as Error).message);
    }

    clearElement(this.saveBtn);
    const icon = document.createElement('i');
    icon.className = 'mdi mdi-content-save';
    this.saveBtn.appendChild(icon);
    this.saveBtn.appendChild(document.createTextNode(' Save'));
    this.updateToolbar();
  }

  private showMessage(type: 'success' | 'danger' | 'warning' | 'info', text: string): void {
    clearElement(this.messageArea);
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.setAttribute('role', 'alert');
    alert.textContent = text;
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'btn-close';
    closeBtn.setAttribute('data-bs-dismiss', 'alert');
    alert.appendChild(closeBtn);
    this.messageArea.appendChild(alert);
  }

  private showConflict(): void {
    clearElement(this.messageArea);
    const alert = document.createElement('div');
    alert.className = 'alert alert-warning';
    alert.setAttribute('role', 'alert');
    alert.textContent = 'This node was modified by another user. ';
    const reloadBtn = document.createElement('button');
    reloadBtn.type = 'button';
    reloadBtn.className = 'btn btn-sm btn-outline-warning ms-2';
    reloadBtn.textContent = 'Reload';
    reloadBtn.addEventListener('click', () => window.location.reload());
    alert.appendChild(reloadBtn);
    this.messageArea.appendChild(alert);
  }

  private bindKeyboard(): void {
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        if (e.shiftKey) {
          e.preventDefault();
          this.redo();
        } else {
          e.preventDefault();
          this.undo();
        }
      }
    });
  }

  private bindBeforeUnload(): void {
    window.addEventListener('beforeunload', (e: BeforeUnloadEvent) => {
      if (this.isDirty()) {
        e.preventDefault();
      }
    });
  }
}

// Entry point
const config = (window as unknown as { WAVELENGTH_EDITOR_CONFIG?: EditorConfig }).WAVELENGTH_EDITOR_CONFIG;
if (config) {
  const container = document.getElementById('wavelength-editor-container');
  if (container) {
    new WavelengthEditor(container, config);
  }
}
