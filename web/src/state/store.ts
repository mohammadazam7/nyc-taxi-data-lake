import { create } from "zustand";
import type { Range, Slot } from "../data/derive";

export type Metric = "trips" | "revenue" | "avg_distance_mi";
export type CameraPreset = "orbit" | "top" | "street";

interface ExplorerState {
  range: Range | null; // null = every day in the report
  metric: Metric;
  hovered: Slot | null;
  focused: Slot | null;
  camera: CameraPreset;
  hour: number | null; // the hour the day player is on, null when off
  playing: boolean;
  selected: Slot | null; // the bar the visitor clicked; drives the camera and the detail panel
  setHour: (hour: number | null) => void;
  setPlaying: (playing: boolean) => void;
  setSelected: (slot: Slot | null) => void;
  setRange: (range: Range | null) => void;
  setMetric: (metric: Metric) => void;
  setHovered: (slot: Slot | null) => void;
  setFocused: (slot: Slot | null) => void;
  setCamera: (camera: CameraPreset) => void;
}

/** One store shared by the 3D scene and every 2D panel. */
export const useExplorer = create<ExplorerState>((set) => ({
  range: null,
  metric: "trips",
  hovered: null,
  focused: null,
  camera: "orbit",
  hour: null,
  playing: false,
  selected: null,
  setHour: (hour) => set({ hour }),
  setPlaying: (playing) => set((s) => ({ playing, hour: playing && s.hour == null ? 0 : s.hour })),
  setSelected: (selected) => set({ selected, focused: null }),
  setRange: (range) => set({ range }),
  setMetric: (metric) => set({ metric }),
  setHovered: (hovered) => set({ hovered }),
  setFocused: (focused) => set({ focused }),
  setCamera: (camera) => set({ camera }),
}));
