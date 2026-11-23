/**
 * directorShotlist.ts — cermin TypeScript dari scripts/director/story-shotlist.json.
 * Nilai spek dipakai persis; eye/target/roll/sunDirection/probeCenter adalah
 * default turunan (derived: true di JSON) karena TIDAK ada di spek.
 * JSON adalah kontrak; file ini dipakai Remotion agar komposisi tidak perlu
 * resolveJsonModule (proyek ini belum punya tsconfig).
 */
export type Shot = {
  id: string;
  startFrame: number;
  endFrame: number;
  act: 1 | 2 | 3 | 4;
  actTitle: string;
  shotSize: string;
  movement: string;
  lensMm: number;
  fStop: number;
  focusDistStart: number;
  focusDistEnd: number;
  dofStrength: number;
  shake: number;
  bloomBoost: number;
  eyeStart: [number, number, number];
  eyeEnd: [number, number, number];
  targetStart: [number, number, number];
  targetEnd: [number, number, number];
  rollStartDeg: number;
  rollEndDeg: number;
  derived: boolean;
};

export const WORLD = {
  earthCenter: [28, 4, -52] as [number, number, number],
  earthRadius: 17.5,
  palette: { bg: '#050814', cyan: '#38bdf8', gold: '#f59e0b', red: '#ef4444' },
  width: 1080,
  height: 1920,
  fps: 30,
  durationFrames: 600,
};

export const SHOTS: Shot[] = [
  { id: 'SC01_A', startFrame: 0, endFrame: 89, act: 1, actTitle: 'Kesunyian', shotSize: 'ELS', movement: 'Slow Dolly', lensMm: 24, fStop: 2.8, focusDistStart: 30.0, focusDistEnd: 24.0, dofStrength: 0.35, shake: 0, bloomBoost: 1.0, eyeStart: [-30, 10, 38], eyeEnd: [-24, 8, 30], targetStart: [0, 0, 0], targetEnd: [4, 1, -6], rollStartDeg: 0, rollEndDeg: 0, derived: true },
  { id: 'SC01_B', startFrame: 90, endFrame: 149, act: 1, actTitle: 'Kesunyian', shotSize: 'MS', movement: 'Orbit Push', lensMm: 38, fStop: 2.2, focusDistStart: 12.0, focusDistEnd: 9.0, dofStrength: 0.5, shake: 0, bloomBoost: 1.0, eyeStart: [14, 4, 18], eyeEnd: [10, 3, 12], targetStart: [0, 0, 0], targetEnd: [0, 0, 0], rollStartDeg: 0, rollEndDeg: 0, derived: true },
  { id: 'SC02_A', startFrame: 150, endFrame: 219, act: 2, actTitle: 'Pencarian', shotSize: 'WS', movement: 'Arc + Rack Focus', lensMm: 32, fStop: 2.2, focusDistStart: 11.4, focusDistEnd: 48.0, dofStrength: 0.8, shake: 0, bloomBoost: 1.1, eyeStart: [-16, 6, 20], eyeEnd: [16, 5, -14], targetStart: [0, 0, 0], targetEnd: [0, 0, 0], rollStartDeg: 0, rollEndDeg: 0, derived: true },
  { id: 'SC02_B', startFrame: 220, endFrame: 299, act: 2, actTitle: 'Pencarian', shotSize: 'OTS', movement: 'Past Dish', lensMm: 42, fStop: 2.4, focusDistStart: 8.0, focusDistEnd: 10.0, dofStrength: 0.45, shake: 0.15, bloomBoost: 1.0, eyeStart: [3, 2, 9], eyeEnd: [-2, 1.5, 6], targetStart: [0, 0, -2], targetEnd: [0, 0, -2], rollStartDeg: 0, rollEndDeg: 0, derived: true },
  { id: 'SC03_A', startFrame: 300, endFrame: 374, act: 3, actTitle: 'Transmisi', shotSize: 'ECU', movement: 'Hull-Cam', lensMm: 38, fStop: 2.2, focusDistStart: 1.8, focusDistEnd: 1.5, dofStrength: 0.7, shake: 0.1, bloomBoost: 1.2, eyeStart: [1.2, 0.6, 2.2], eyeEnd: [0.9, 0.5, 1.6], targetStart: [0, 0, 0], targetEnd: [0, 0, 0], rollStartDeg: 0, rollEndDeg: 0, derived: true },
  { id: 'SC03_B', startFrame: 375, endFrame: 449, act: 3, actTitle: 'Transmisi', shotSize: 'MCU', movement: 'Whip Chase Along Beam + camera shake', lensMm: 28, fStop: 2.4, focusDistStart: 6.0, focusDistEnd: 14.0, dofStrength: 0.6, shake: 0.6, bloomBoost: 1.35, eyeStart: [8, 2, 10], eyeEnd: [-6, 1.5, 4], targetStart: [0, 0, -4], targetEnd: [0, 0, -4], rollStartDeg: -2, rollEndDeg: 3, derived: true },
  { id: 'SC04_A', startFrame: 450, endFrame: 599, act: 4, actTitle: 'Terhubung', shotSize: 'ELS', movement: 'Serene Horizon Pullback', lensMm: 26, fStop: 4.0, focusDistStart: 36.0, focusDistEnd: 48.0, dofStrength: 0.25, shake: 0, bloomBoost: 1.15, eyeStart: [6, 3, 14], eyeEnd: [34, 10, 30], targetStart: [14, 2, -26], targetEnd: [28, 4, -52], rollStartDeg: 0, rollEndDeg: 0, derived: true },
];

export function shotForFrame(frame: number): Shot {
  return SHOTS.find((s) => frame >= s.startFrame && frame <= s.endFrame) || SHOTS[SHOTS.length - 1];
}

export function focusAt(frame: number, shot: Shot): number {
  const n = Math.max(1, shot.endFrame - shot.startFrame);
  const t = (frame - shot.startFrame) / n;
  return shot.focusDistStart + (shot.focusDistEnd - shot.focusDistStart) * t;
}

export function batteryPercent(frame: number): number {
  return 12 - (10 * frame) / 599;
}

export function actColor(act: number): string {
  if (act === 1) return WORLD.palette.cyan;
  if (act === 2) return WORLD.palette.gold;
  if (act === 3) return WORLD.palette.red;
  return WORLD.palette.cyan;
}
