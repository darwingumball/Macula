import { create } from "zustand";
import type { Device, Profile, Region } from "./types";

interface AppState {
  profile: Profile | null;
  devices: Device[];
  regions: Region[];
  activeDeviceId: string | null;

  setProfile: (p: Profile) => void;
  setDevices: (d: Device[]) => void;
  addDevice: (d: Device) => void;
  updateDevice: (d: Device) => void;
  removeDevice: (id: string) => void;
  setRegions: (r: Region[]) => void;
  addRegion: (r: Region) => void;
  updateRegion: (r: Region) => void;
  removeRegion: (id: string) => void;
  setActiveDevice: (id: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  profile: null,
  devices: [],
  regions: [],
  activeDeviceId: null,

  setProfile: (profile) => set({ profile }),
  setDevices: (devices) => set({ devices }),
  addDevice: (d) => set((s) => ({ devices: [...s.devices, d] })),
  updateDevice: (d) =>
    set((s) => ({ devices: s.devices.map((x) => (x.id === d.id ? d : x)) })),
  removeDevice: (id) =>
    set((s) => ({ devices: s.devices.filter((x) => x.id !== id) })),
  setRegions: (regions) => set({ regions }),
  addRegion: (r) => set((s) => ({ regions: [...s.regions, r] })),
  updateRegion: (r) =>
    set((s) => ({ regions: s.regions.map((x) => (x.id === r.id ? r : x)) })),
  removeRegion: (id) =>
    set((s) => ({ regions: s.regions.filter((x) => x.id !== id) })),
  setActiveDevice: (activeDeviceId) => set({ activeDeviceId }),
}));
