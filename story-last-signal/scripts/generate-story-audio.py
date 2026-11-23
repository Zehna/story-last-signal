#!/usr/bin/env python3
"""StoryLastSignal Tahap 2 - generate-story-audio.py
Sintesis audio 48kHz stereo 20 detik (numpy + WAV), lalu mastering:
  SoX wet  (highpass 110, reverb 64 52 86 100 18 2)
  amix dry+wet via ffmpeg
  loudnorm two-pass -> -14.0 LUFS, -1.0 dBTP, LRA 9.0
Output: public/sfx/last-signal.wav (verifikasi loudness akhir dengan ffmpeg loudnorm)
Semua sumber deterministik (seed tetap); tidak ada rekaman eksternal.
"""
import json, re, subprocess, sys, wave
from pathlib import Path
import numpy as np

SR = 48000
DUR = 20.0
N = int(SR * DUR)
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "sfx" / "last-signal.wav"
TMP = ROOT / "out" / "audio_tmp"
rng = np.random.default_rng(20261123)

def t_axis():
    return np.arange(N, dtype=np.float64) / SR

def sine(freq, dur, t0=0.0, amp=1.0, phase=0.0):
    t = np.arange(int(SR * dur), dtype=np.float64) / SR
    return amp * np.sin(2 * np.pi * freq * t + phase)

def chirp(f0, f1, dur, amp=1.0, quad=False):
    n = int(SR * dur)
    t = np.arange(n, dtype=np.float64) / SR
    if quad:
        f = f0 + (f1 - f0) * (t / dur) ** 2
    else:
        f = f0 + (f1 - f0) * (t / dur)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return amp * np.sin(ph)

def env_adsr(n, a=0.01, d=0.1, s=0.7, r=0.2):
    e = np.ones(n)
    na, nd, nr = int(SR * a), int(SR * d), int(SR * r)
    if na: e[:na] = np.linspace(0, 1, na)
    if nd: e[na:na + nd] = np.linspace(1, s, nd)
    if nr: e[-nr:] = np.linspace(s, 0, nr)
    return e

def bandpass(x, lo, hi):
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    mask = (freqs >= lo) & (freqs <= hi)
    return np.fft.irfft(X * mask, n=len(x))

def add(mix, sig, t0, pan=0.0):
    """Tambah sinyal mono ke mix stereo [2, N] mulai t0 detik, pan -1..1."""
    i0 = int(t0 * SR)
    n = min(len(sig), N - i0)
    if n <= 0:
        return
    l = np.cos((pan + 1) * np.pi / 4)
    r = np.sin((pan + 1) * np.pi / 4)
    mix[0, i0:i0 + n] += sig[:n] * l
    mix[1, i0:i0 + n] += sig[:n] * r

def noise_burst(dur, amp=1.0):
    n = int(SR * dur)
    x = rng.normal(0, 1, n)
    return amp * x * np.exp(-np.arange(n) / (SR * dur * 0.35))

def write_wav(path, mix):
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = np.max(np.abs(mix)) or 1.0
    data = np.clip(mix / peak * 0.9, -1, 1)
    inter = np.empty((2 * N,), dtype=np.int16)
    inter[0::2] = (data[0] * 32767).astype(np.int16)
    inter[1::2] = (data[1] * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(inter.tobytes())
    return peak

def sub_impact(mix, t0, amp=0.9):
    n = int(SR * 0.5)
    t = np.arange(n) / SR
    sig = amp * np.sin(2 * np.pi * 45 * t) * np.exp(-t * 9)
    add(mix, sig, t0)
    add(mix, noise_burst(0.05, 0.5), t0)

def synth():
    mix = np.zeros((2, N))
    t = t_axis()
    # --- Act 1 (0-5 dtk): drone 49 Hz + harmonik, VHF static ---
    a1 = (t < 5).astype(float) * np.clip((5 - t) * 2, 0, 1)
    drone = (np.sin(2*np.pi*49*t) * 0.5 + np.sin(2*np.pi*98*t) * 0.22
             + np.sin(2*np.pi*147*t) * 0.12 + np.sin(2*np.pi*196*t) * 0.07) * 0.30
    mix[0] += drone * a1; mix[1] += drone * a1
    static = bandpass(rng.normal(0, 1, N), 900, 4200) * 0.05
    mix[0] += static * a1; mix[1] += static * a1
    for tb, pan in ((1.2, -0.3), (3.4, 0.3)):
        b = sine(587.33, 0.15, amp=0.25) * env_adsr(int(SR*0.15), a=0.005, d=0.05, s=0.6, r=0.05)
        add(mix, b, tb, pan)
    for tc in (2.0, 4.1):
        add(mix, noise_burst(0.03, 0.4), tc)
    # --- Act 2 (5-10 dtk): servo reaction-wheel, 4 tiupan RCS, gimbal latch, sonar ---
    a2 = ((t >= 5) & (t < 10)).astype(float)
    servo = chirp(180, 420, 5.0, amp=0.12) * (0.7 + 0.3*np.sin(2*np.pi*7*np.arange(int(SR*5))/SR))
    add(mix, servo, 5.0, 0.0)
    for tp, pan in ((5.6, -0.7), (6.4, -0.2), (7.1, 0.3), (8.3, 0.8)):
        puff = bandpass(noise_burst(0.35, 0.8), 800, 3000)
        add(mix, puff, tp, pan)
    add(mix, noise_burst(0.04, 0.6), 7.42)
    add(mix, sine(1240, 0.12, amp=0.3) * np.exp(-np.arange(int(SR*0.12))/(SR*0.04)), 7.42, 0.1)
    ping = sine(880, 1.2, amp=0.35) * np.exp(-np.arange(int(SR*1.2))/(SR*0.35))
    ping += sine(1760, 1.2, amp=0.1) * np.exp(-np.arange(int(SR*1.2))/(SR*0.3))
    add(mix, ping, 9.0, 0.0)
    # --- Act 3 (10-15 dtk): riser kapasitor, reactor rumble, pulse + FSK ---
    riser = chirp(280, 1200, 5.0, amp=0.16, quad=True)
    add(mix, riser, 10.0, 0.0)
    rumble = bandpass(rng.normal(0, 1, N), 40, 80) * 0.25 + np.sin(2*np.pi*55*t) * 0.10
    a3 = ((t >= 10) & (t < 15)).astype(float)
    mix[0] += rumble * a3; mix[1] += rumble * a3
    for i in range(10):
        add(mix, sine(2400, 0.06, amp=0.22) * np.exp(-np.arange(int(SR*0.06))/(SR*0.02)), 10.2 + i*0.45, -0.4 + 0.08*i)
    bits = [1, 0, 1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 0, 1, 1]
    for i, b in enumerate(bits):
        f = 2200 if b else 1200
        add(mix, sine(f, 0.09, amp=0.18), 12.0 + i*0.11, 0.0)
    # --- Act 4 (15-20 dtk): pad akor hangat, 5 chime, squelch, double tone ---
    a4 = (t >= 15).astype(float) * np.clip((t - 15) * 2, 0, 1)
    pad = sum(np.sin(2*np.pi*f*t) * a for f, a in ((261.63, 0.10), (329.63, 0.08), (392.00, 0.08), (523.25, 0.05)))
    mix[0] += pad * a4; mix[1] += pad * a4
    for tc, f in ((15.5, 587.33), (16.2, 739.99), (16.9, 880.0), (17.6, 1174.66), (18.3, 1760.0)):
        ch = sine(f, 1.0, amp=0.28) * np.exp(-np.arange(int(SR*1.0))/(SR*0.30))
        ch += sine(f*2, 1.0, amp=0.08) * np.exp(-np.arange(int(SR*1.0))/(SR*0.2))
        add(mix, ch, tc, 0.0)
    add(mix, bandpass(noise_burst(0.4, 0.5), 1500, 5000), 15.05)
    for tt in (19.0, 19.25):
        add(mix, sine(2475, 0.12, amp=0.25), tt, 0.0)
    for ts in (4.98, 10.00, 15.10):
        sub_impact(mix, ts)
    return mix

def run(cmd, what):
    print("+", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit(f"{what} gagal (rc={r.returncode})")
    return r

def loudnorm_measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                        "loudnorm=I=-14:TP=-1:LRA=9:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^}]*\}", r.stderr, re.S)
    if not m:
        print(r.stderr[-2000:])
        raise SystemExit("loudnorm measure gagal: JSON tidak ditemukan")
    return json.loads(m.group(0))

def main():
    TMP.mkdir(parents=True, exist_ok=True)
    mix = synth()
    dry = TMP / "dry.wav"
    peak = write_wav(dry, mix)
    print(f"dry: {dry} peak_sebelum_normalisasi={peak:.3f} durasi={DUR}s {SR}Hz stereo")
    wet = TMP / "wet.wav"
    run(["sox", str(dry), str(wet), "highpass", "110",
         "reverb", "64", "52", "86", "100", "18", "2"], "SoX wet")
    mixed = TMP / "mixed.wav"
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(dry), "-i", str(wet),
         "-filter_complex", "amix=inputs=2:duration=first:dropout_transition=0",
         str(mixed)], "amix dry+wet")
    m = loudnorm_measure(mixed)
    print("loudnorm pass 1 (terukur):", {k: m.get(k) for k in
          ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")})
    af = ("loudnorm=I=-14:TP=-1.3:LRA=9:measured_I=%s:measured_TP=%s:measured_LRA=%s"  # TP -1.3: margin 0.3 dB agar setelah resample ke 48kHz hasil akhir tetap <= -1.0 dBTP
          ":measured_thresh=%s:offset=%s:linear=true:print_format=json"
          % (m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"], m["target_offset"]))
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(mixed), "-af", af, "-ar", "48000", str(OUT)],  # loudnorm menaikkan ke 192kHz; kembalikan ke 48kHz
        "loudnorm pass 2")
    v = loudnorm_measure(OUT)
    print("loudnorm VERIFIKASI akhir:", {k: v.get(k) for k in
          ("input_i", "input_tp", "input_lra", "input_thresh")})
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration,size", "-of", "json", str(OUT)],
                           capture_output=True, text=True)
    info = json.loads(probe.stdout)["format"]
    print(f"SELESAI: {OUT} ({OUT.stat().st_size} byte) durasi={float(info['duration']):.2f}s "
          f"terukur_I={v['input_i']} LUFS TP={v['input_tp']} dBTP LRA={v['input_lra']}")

if __name__ == "__main__":
    main()
