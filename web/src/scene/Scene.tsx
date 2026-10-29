import { OrbitControls } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import gsap from "gsap";
import { useEffect, useRef } from "react";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import { useExplorer, type CameraPreset } from "../state/store";
import { DemandLandscape } from "./DemandLandscape";

const PRESETS: Record<CameraPreset, { position: [number, number, number]; target: [number, number, number] }> = {
  orbit: { position: [-19, 17, 25], target: [0, 1.2, 0] },
  top: { position: [0, 36, 0.01], target: [0, 0, 0] },
  street: { position: [-21, 4, 9], target: [2, 2.5, 0] },
};

function CameraRig({ reducedMotion }: { reducedMotion: boolean }) {
  const camera = useThree((s) => s.camera);
  const controls = useRef<OrbitControlsImpl>(null);
  const preset = useExplorer((s) => s.camera);
  const focused = useExplorer((s) => s.focused);
  const selected = useExplorer((s) => s.selected);
  const playing = useExplorer((s) => s.playing);

  useEffect(() => {
    const p = PRESETS[preset];
    const c = controls.current;
    if (!c) return;
    const d = reducedMotion ? 0 : 1.4;
    const tl = gsap.timeline();
    tl.to(camera.position, { x: p.position[0], y: p.position[1], z: p.position[2], duration: d, ease: "power3.inOut" }, 0);
    tl.to(c.target, { x: p.target[0], y: p.target[1], z: p.target[2], duration: d, ease: "power3.inOut", onUpdate: () => c.update() }, 0);
    return () => {
      tl.kill();
    };
  }, [preset, camera, reducedMotion]);

  // Clicking a bar flies the camera in on it; clearing the selection flies back.
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    const d = reducedMotion ? 0 : 1.2;
    const p = PRESETS[preset];
    const look: [number, number, number] = selected
      ? [selected.hour - 11.5, 3, selected.day - 3]
      : p.target;
    const eye: [number, number, number] = selected
      ? [look[0] - 10, 15, look[2] + 16]
      : p.position;
    const tl = gsap.timeline();
    tl.to(camera.position, { x: eye[0], y: eye[1], z: eye[2], duration: d, ease: "power3.inOut" }, 0);
    tl.to(c.target, { x: look[0], y: look[1], z: look[2], duration: d, ease: "power3.inOut", onUpdate: () => c.update() }, 0);
    return () => {
      tl.kill();
    };
  }, [selected, camera, reducedMotion]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <OrbitControls
      ref={controls}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={10}
      maxDistance={48}
      maxPolarAngle={Math.PI / 2.08}
      autoRotate={!reducedMotion && !focused && !selected && !playing && preset === "orbit"}
      autoRotateSpeed={0.35}
    />
  );
}

interface Props { grid: number[][]; reducedMotion: boolean; label: string }

/** The WebGL canvas. Loaded lazily so the page paints before three.js arrives. */
export default function Scene({ grid, reducedMotion, label }: Props) {
  const p = PRESETS.orbit;
  return (
    <Canvas
      shadows
      dpr={[1, 2]}
      camera={{ position: p.position, fov: 38, near: 0.1, far: 200 }}
      frameloop={reducedMotion ? "demand" : "always"}
      aria-label={label}
      role="img"
      gl={{ antialias: true, powerPreference: "high-performance" }}
    >
      <color attach="background" args={["#0b0f18"]} />
      <fog attach="fog" args={["#0b0f18", 34, 70]} />
      <ambientLight intensity={0.35} />
      <hemisphereLight args={["#9cc4ff", "#1a1206", 0.45]} />
      <directionalLight position={[-12, 22, 10]} intensity={1.4} castShadow shadow-mapSize={[1024, 1024]}>
        <orthographicCamera attach="shadow-camera" args={[-20, 20, 12, -12, 1, 60]} />
      </directionalLight>
      <pointLight position={[12, 9, -6]} intensity={40} color="#fc4a1a" distance={30} />
      <DemandLandscape grid={grid} reducedMotion={reducedMotion} />
      <CameraRig reducedMotion={reducedMotion} />
    </Canvas>
  );
}
