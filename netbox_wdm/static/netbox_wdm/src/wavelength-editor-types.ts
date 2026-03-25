export interface ChannelData {
  id: number;
  grid_position: number;
  wavelength_nm: number;
  label: string;
  mux_front_port_id: number | null;
  mux_front_port_name: string | null;
  demux_front_port_id: number | null;
  demux_front_port_name: string | null;
  status: 'available' | 'reserved' | 'active';
  service_name: string | null;
}

export interface PortData {
  id: number;
  name: string;
}

export interface EditorConfig {
  nodeId: number;
  nodeType: string;
  fiberType: 'duplex' | 'single_fiber';
  lastUpdated: string;
  applyUrl: string;
  channels: ChannelData[];
  availablePorts: PortData[];
}
