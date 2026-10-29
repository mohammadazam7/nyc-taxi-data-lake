import { Html } from "@react-three/drei";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { rampColor } from "../atlas/tokens";
import { WEEKDAYS, hourLabel, type Slot } from "../data/derive";
import { useExplorer } from "../state/store";

const COLS = 24;
const ROWS = 7;
const PITCH = 1; // grid spacing in world units
const SIZE = 0.78; // bar footprint
const MAX_H = 7.5;

interface Props {
  grid: number[][];
  reducedMotion: boolean;
}

const tmp = new THREE.Object3D();
const color = new THREE.Color();
const white = new THREE.Color("#ffffff");

/**
 * 168 bars, one per weekday and hour, drawn as ONE instanced mesh: a single draw call,
 * so the scene stays at 60 fps on integrated GPUs. Height and colour encode pickups.
 */
export function DemandLandscape({ grid, reducedMotion }: Props) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const grow = useRef({ t: reducedMotion ? 1 : 0 });
  const hovered = useExplorer((s) => s.hovered);
  const focused = useExplorer((s) => s.focused);
  const setHovered = useExplorer((s) => s.setHovered);
  const hour = useExplorer((s) => s.hour);
  const selected = useExplorer((s) => s.selected);
  const setSelected = useExplorer((s) => s.setSelected);
  const sweep = useRef<THREE.Mesh>(null);
  const sweepX = useRef(0);

  const cells = useMemo(() => {
    const flat = grid.flat();
    const lo = Math.min(...flat);
    const hi = Math.max(...flat);
    return grid.flatMap((row, day) =>
      row.map((trips, hour) => ({ day, hour, trips, t: hi > lo ? (trips - lo) / (hi - lo) : 0 })),
    );
  }, [grid]);

  // Staggered rise on first load; skipped under reduced motion.
  useEffect(() => {
    if (reducedMotion) return;
    const tween = gsap.to(grow.current, { t: 1, duration: 1.6, ease: "power3.out", delay: 0.2 });
    return () => {
      tween.kill();
    };
  }, [reducedMotion]);

  useLayoutEffect(() => {
    const m = mesh.current;
    if (!m) return;
    cells.forEach((c, i) => {
      const [r, g, b] = rampColor(c.t);
      m.setColorAt(i, color.setRGB(r, g, b, THREE.SRGBColorSpace));
    });
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, [cells]);

  useFrame(() => {
    const m = mesh.current;
    if (!m) return;
    const g = grow.current.t;
    const active = hovered ?? focused ?? selected;
    const dimOthers = Boolean(focused ?? selected);
    // The light plane glides to the player's hour instead of jumping.
    if (sweep.current) {
      const target = hour == null ? sweepX.current : (hour - (COLS - 1) / 2) * PITCH;
      sweepX.current += (target - sweepX.current) * 0.18;
      sweep.current.position.x = sweepX.current;
      const mat = sweep.current.material as THREE.MeshBasicMaterial;
      mat.opacity += ((hour == null ? 0 : 0.16) - mat.opacity) * 0.15;
    }
    cells.forEach((c, i) => {
      // Bars rise from the front row backwards, so the wave reads as depth.
      const local = Math.max(0, Math.min(1, g * 1.6 - (c.hour / COLS) * 0.3 - (c.day / ROWS) * 0.3));
      const h = (0.12 + c.t * MAX_H) * local + 0.001;
      tmp.position.set((c.hour - (COLS - 1) / 2) * PITCH, h / 2, (c.day - (ROWS - 1) / 2) * PITCH);
      tmp.scale.set(SIZE, h, SIZE);
      tmp.updateMatrix();
      m.setMatrixAt(i, tmp.matrix);
      const isActive = active && active.day === c.day && active.hour === c.hour;
      const [r, gg, b] = rampColor(c.t);
      color.setRGB(r, gg, b, THREE.SRGBColorSpace);
      if (isActive) color.lerp(white, 0.65);
      else if (dimOthers) color.multiplyScalar(0.35);
      else if (hour != null && c.hour !== hour) color.multiplyScalar(0.42);
      else if (hour != null) color.lerp(white, 0.18);
      m.setColorAt(i, color);
    });
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  });

  const onMove = (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    const c = e.instanceId != null ? cells[e.instanceId] : undefined;
    if (c && (hovered?.day !== c.day || hovered?.hour !== c.hour)) setHovered({ day: c.day, hour: c.hour, trips: c.trips });
  };

  const label = hovered ?? focused ?? selected;
  const labelPos = label ? cellTop(label, cells) : null;

  return (
    <group>
      <instancedMesh
        ref={mesh}
        args={[undefined, undefined, cells.length]}
        castShadow
        receiveShadow
        onPointerMove={onMove}
        onPointerOut={() => setHovered(null)}
        onClick={(e) => {
          e.stopPropagation();
          const c = e.instanceId != null ? cells[e.instanceId] : undefined;
          if (!c) return;
          const same = selected?.day === c.day && selected.hour === c.hour;
          setSelected(same ? null : { day: c.day, hour: c.hour, trips: c.trips });
        }}
      >
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial roughness={0.42} metalness={0.15} />
      </instancedMesh>

      <mesh ref={sweep} position={[0, MAX_H / 2 + 0.2, 0]}>
        <boxGeometry args={[0.96, MAX_H + 0.6, ROWS * PITCH + 0.6]} />
        <meshBasicMaterial color="#4fa3ff" transparent opacity={0} depthWrite={false} blending={THREE.AdditiveBlending} />
      </mesh>

      <mesh rotation-x={-Math.PI / 2} position-y={-0.01} receiveShadow onClick={() => setSelected(null)}>
        <planeGeometry args={[COLS * PITCH + 3, ROWS * PITCH + 3]} />
        <meshStandardMaterial color="#0f1420" roughness={0.95} />
      </mesh>
      <gridHelper args={[COLS + 3, COLS + 3, "#1c2433", "#141a26"]} position-y={0.001} scale={[1, 1, (ROWS + 3) / (COLS + 3)]} />

      {WEEKDAYS.map((d, i) => (
        <Html key={d} position={[-(COLS / 2) - 1.1, 0, (i - (ROWS - 1) / 2) * PITCH]} center className="axis-label">
          {d}
        </Html>
      ))}
      {[0, 3, 6, 9, 12, 15, 18, 21].map((h) => (
        <Html key={h} position={[(h - (COLS - 1) / 2) * PITCH, 0, ROWS / 2 + 1.2]} center className="axis-label">
          {hourLabel(h)}
        </Html>
      ))}
      {label && labelPos && (
        <Html position={labelPos} center className="pointer-events-none">
          <div className="scene-callout">
            {WEEKDAYS[label.day]} {hourLabel(label.hour)} · {label.trips.toLocaleString("en-US")}
          </div>
        </Html>
      )}
    </group>
  );
}

function cellTop(slot: Slot, cells: { day: number; hour: number; t: number }[]): [number, number, number] {
  const c = cells.find((x) => x.day === slot.day && x.hour === slot.hour);
  const h = 0.12 + (c?.t ?? 0) * MAX_H;
  return [(slot.hour - (COLS - 1) / 2) * PITCH, h + 0.9, (slot.day - (ROWS - 1) / 2) * PITCH];
}
