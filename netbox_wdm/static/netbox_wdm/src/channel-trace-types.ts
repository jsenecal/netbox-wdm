export interface PortInfo {
  id: number;
  name: string;
  url: string;
}

export interface HopData {
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
  is_origin: boolean;
}

export interface CableSegmentElement {
  type: 'rear_port' | 'cable' | 'front_port';
  id: number;
  name: string;
  device?: string;
  label?: string;
  status?: string;
  color?: string;
  url: string;
}

export interface CableSegment {
  from_hop: number;
  to_hop: number;
  path: CableSegmentElement[];
}

export interface TraceData {
  channel_id: number;
  wavelength_path_id: number;
  wavelength_nm: number;
  grid_position: number;
  is_complete: boolean;
  is_active: boolean;
  hops: HopData[];
  cable_segments: CableSegment[];
}
