export interface PortInfo {
  id: number;
  name: string;
  url: string;
}

export interface PathElement {
  sequence: number;
  node_id: number;
  node_name: string;
  node_url: string;
  channel_id: number;
  channel_label: string;
  channel_url: string;
  wavelength_nm: number;
  mux_port: PortInfo | null;
  demux_port: PortInfo | null;
  mux_connected: boolean;
  demux_connected: boolean;
}

export interface CableSegmentItem {
  type: 'rear_port' | 'cable' | 'front_port' | 'circuit_termination';
  id: number;
  name: string;
  url: string;
  device?: string;
  label?: string;
  status?: string;
  color?: string;
}

export interface CableSegment {
  from_sequence: number;
  to_sequence: number;
  items: CableSegmentItem[];
}

export interface TraceData {
  channel_id: number;
  wavelength_path_id: number | null;
  wavelength_nm: number | null;
  grid_position: number;
  is_complete: boolean;
  is_active: boolean;
  is_valid: boolean;
  elements: PathElement[];
  cable_segments: CableSegment[];
}
