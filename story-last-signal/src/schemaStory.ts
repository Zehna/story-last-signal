/**
 * schemaStory.ts — validasi manual kontrak story-shotlist.json.
 * (Tidak memakai zod: dependensi itu tidak ada di package.json proyek.)
 * Dipakai render-story.yml / skrip CI untuk menolak shotlist yang rusak
 * sebelum render 600 frame dimulai.
 */
import { SHOTS, WORLD } from './lib/directorShotlist';

export type ShotlistError = string;

export function validateShotlist(): ShotlistError[] {
  const errs: ShotlistError[] = [];
  if (WORLD.width !== 1080 || WORLD.height !== 1920) errs.push('resolusi harus 1080x1920');
  if (WORLD.fps !== 30) errs.push('fps harus 30');
  if (WORLD.durationFrames !== 600) errs.push('durasi harus 600 frame');
  if (WORLD.earthRadius !== 17.5) errs.push('earthRadius harus 17.5');
  const ec = WORLD.earthCenter;
  if (ec[0] !== 28 || ec[1] !== 4 || ec[2] !== -52) errs.push('earthCenter harus [28, 4, -52]');
  let expect = 0;
  for (const s of SHOTS) {
    if (s.startFrame !== expect) errs.push(s.id + ': startFrame harus ' + expect);
    if (s.endFrame < s.startFrame) errs.push(s.id + ': endFrame < startFrame');
    if (s.lensMm <= 0) errs.push(s.id + ': lensMm harus > 0');
    if (s.fStop <= 0) errs.push(s.id + ': fStop harus > 0');
    if (s.focusDistStart <= 0 || s.focusDistEnd <= 0) errs.push(s.id + ': focusDist harus > 0');
    if (s.dofStrength < 0 || s.dofStrength > 1) errs.push(s.id + ': dofStrength di luar 0..1');
    if (s.shake < 0 || s.shake > 1) errs.push(s.id + ': shake di luar 0..1');
    if (s.bloomBoost <= 0) errs.push(s.id + ': bloomBoost harus > 0');
    expect = s.endFrame + 1;
  }
  if (expect !== 600) errs.push('shot terakhir harus berakhir di frame 599');
  return errs;
}

export function assertShotlistValid(): void {
  const errs = validateShotlist();
  if (errs.length > 0) {
    throw new Error('shotlist tidak valid: ' + errs.join('; '));
  }
}
