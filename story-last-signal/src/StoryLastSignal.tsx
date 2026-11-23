/**
 * StoryLastSignal.tsx — komposisi Remotion 4.0.545 / React 19.
 * PENGECUALIAN FONT: proyek ini mengunci Outfit (@fontsource/outfit),
 * komposisi ini memakai Inter & Plus Jakarta Sans (lihat README).
 * Base video: frame PNG render 3D (public/frames/frame_NNNN.png).
 * includeBaseVideo=false dipakai saat render cloud -> PNG transparan
 * (overlay saja, tanpa latar), lalu di-composite dengan ffmpeg.
 * Teks subtitle adalah kalimat turunan (bukan dari spek); shot/lensa/fokus
 * dibaca dari shotlist (src/lib/directorShotlist.ts).
 */
import React from 'react';
import { AbsoluteFill, Audio, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { actColor, batteryPercent, focusAt, shotForFrame, WORLD } from './lib/directorShotlist';
import type { Shot } from './lib/directorShotlist';

const FONT = "'Inter', 'Plus Jakarta Sans', sans-serif";
const FONT_DISPLAY = "'Plus Jakarta Sans', 'Inter', sans-serif";
const CYAN = WORLD.palette.cyan;
const GOLD = WORLD.palette.gold;
const RED = WORLD.palette.red;

function pad4(n: number): string {
  return String(n).padStart(4, '0');
}

function Bracket({ color, top, left, right, bottom }: { color: string; top?: number; left?: number; right?: number; bottom?: number }) {
  const s: React.CSSProperties = { position: 'absolute', width: 64, height: 64, borderColor: color, borderStyle: 'solid', borderWidth: 0 };
  if (top !== undefined) { s.top = top; s.borderTopWidth = 4; }
  if (bottom !== undefined) { s.bottom = bottom; s.borderBottomWidth = 4; }
  if (left !== undefined) { s.left = left; s.borderLeftWidth = 4; }
  if (right !== undefined) { s.right = right; s.borderRightWidth = 4; }
  return <div style={s} />;
}

export function CinemaViewfinderOverlay({ act }: { act: number }) {
  const color = actColor(act);
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 180, background: 'linear-gradient(to bottom, rgba(5,8,20,0.65), rgba(5,8,20,0))' }} />
      <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: 220, background: 'linear-gradient(to top, rgba(5,8,20,0.65), rgba(5,8,20,0))' }} />
      <Bracket color={color} top={48} left={48} />
      <Bracket color={color} top={48} right={48} />
      <Bracket color={color} bottom={48} left={48} />
      <Bracket color={color} bottom={48} right={48} />
      <div style={{ position: 'absolute', top: '50%', left: '50%', width: 28, height: 28, transform: 'translate(-50%, -50%)', opacity: 0.7 }}>
        <div style={{ position: 'absolute', top: 13, left: 0, right: 0, height: 2, background: color }} />
        <div style={{ position: 'absolute', left: 13, top: 0, bottom: 0, width: 2, background: color }} />
      </div>
    </AbsoluteFill>
  );
}

export function StoryHud({ frame, shot }: { frame: number; shot: Shot }) {
  const pct = batteryPercent(frame);
  const filled = Math.max(1, Math.ceil((pct / 12) * 5));
  const focus = focusAt(frame, shot);
  const color = actColor(shot.act);
  const rows: Array<[string, string]> = [
    ['SHOT', shot.id],
    ['SIZE', shot.shotSize],
    ['LENS', shot.lensMm + 'mm f/' + shot.fStop.toFixed(1)],
    ['MOVE', shot.movement],
    ['FOCUS', focus.toFixed(1) + 'm'],
  ];
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', fontFamily: FONT }}>
      <div style={{ position: 'absolute', top: 72, left: 72, display: 'flex', alignItems: 'center', gap: 16 }}>
        <span style={{ background: color, color: '#050814', fontWeight: 800, fontSize: 26, letterSpacing: 2, padding: '8px 16px', borderRadius: 999 }}>
          {'CASSINI // ACT ' + shot.act + ' — ' + shot.actTitle.toUpperCase()}
        </span>
        <span style={{ color: '#fff', fontSize: 24, letterSpacing: 2, opacity: 0.9 }}>{'BAT ' + pct.toFixed(0) + '%'}</span>
        <span style={{ display: 'flex', gap: 6 }}>
          {[0, 1, 2, 3, 4].map((i) => (
            <span key={i} style={{ width: 26, height: 14, borderRadius: 3, background: i < filled ? (pct <= 3 ? RED : GOLD) : 'rgba(255,255,255,0.25)' }} />
          ))}
        </span>
      </div>
      <div style={{ position: 'absolute', left: 72, bottom: 96, color: '#fff', fontSize: 24, lineHeight: 1.5, background: 'rgba(5,8,20,0.55)', padding: '14px 20px', borderRadius: 12 }}>
        {rows.map(([k, v]) => (
          <div key={k}><span style={{ color: CYAN, fontWeight: 700, marginRight: 12 }}>{k}</span><span>{v}</span></div>
        ))}
      </div>
    </AbsoluteFill>
  );
}

const SUBTITLES: Array<{ start: number; end: number; text: string }> = [
  { start: 0, end: 89, text: 'Sinyal terakhir dari orbit Saturnus.' },
  { start: 150, end: 299, text: 'Cassini mencari arah pulang.' },
  { start: 300, end: 449, text: 'Transmisi dimulai. Satu pesan, satu kesempatan.' },
  { start: 505, end: 599, text: 'Sinyal diterima. Terima kasih, Cassini.' },
];

export function CinemaSubtitles({ frame }: { frame: number }) {
  const config = useVideoConfig();
  const cue = SUBTITLES.find((c) => frame >= c.start && frame <= c.end);
  if (!cue) return null;
  const local = frame - cue.start;
  const len = cue.end - cue.start;
  const sIn = spring({ frame: local, fps: config.fps, config: { damping: 200 } });
  const sOut = spring({ frame: len - local, fps: config.fps, config: { damping: 200 } });
  const opacity = interpolate(sIn * sOut, [0, 1], [0, 1]);
  const y = interpolate(sIn, [0, 1], [24, 0]);
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', justifyContent: 'flex-end', alignItems: 'center' }}>
      <div style={{ marginBottom: 300, maxWidth: 900, textAlign: 'center', opacity, transform: 'translateY(' + y + 'px)', fontFamily: FONT }}>
        <span style={{ color: '#fff', fontSize: 40, fontWeight: 600, lineHeight: 1.35, background: 'rgba(5,8,20,0.6)', padding: '10px 22px', borderRadius: 10, boxDecorationBreak: 'clone', WebkitBoxDecorationBreak: 'clone' }}>
          {cue.text}
        </span>
      </div>
    </AbsoluteFill>
  );
}

export function EndingTitleLockup({ frame }: { frame: number }) {
  const config = useVideoConfig();
  if (frame < 505) return null;
  const local = frame - 505;
  const s = spring({ frame: local, fps: config.fps, config: { damping: 12, stiffness: 90 } });
  const opacity = interpolate(s, [0, 1], [0, 1]);
  const scale = interpolate(s, [0, 1], [0.92, 1]);
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', justifyContent: 'center', alignItems: 'center' }}>
      <div style={{ textAlign: 'center', opacity, transform: 'scale(' + scale + ')', fontFamily: FONT_DISPLAY }}>
        <div style={{ color: GOLD, fontSize: 34, letterSpacing: 10, fontWeight: 700 }}>{'SIGNAL RECEIVED'}</div>
        <div style={{ color: '#fff', fontSize: 84, fontWeight: 800, letterSpacing: 2, marginTop: 12 }}>{'SINYAL TERAKHIR'}</div>
        <div style={{ color: '#fff', fontSize: 84, fontWeight: 800, letterSpacing: 2 }}>{'DI ORBIT'}</div>
        <div style={{ width: 160, height: 6, background: CYAN, margin: '28px auto 0', borderRadius: 3 }} />
      </div>
    </AbsoluteFill>
  );
}

export default function StoryLastSignal({ includeBaseVideo = true }: { includeBaseVideo?: boolean }) {
  const frame = useCurrentFrame();
  const shot = shotForFrame(frame);
  return (
    <AbsoluteFill style={{ backgroundColor: includeBaseVideo ? '#050814' : 'transparent', fontFamily: FONT }}>
      {includeBaseVideo ? (
        <Img src={staticFile('frames/frame_' + pad4(frame) + '.png')} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      ) : null}
      <CinemaViewfinderOverlay act={shot.act} />
      <StoryHud frame={frame} shot={shot} />
      <CinemaSubtitles frame={frame} />
      <EndingTitleLockup frame={frame} />
      <Audio src={staticFile('sfx/last-signal.wav')} volume={0.88} />
    </AbsoluteFill>
  );
}
