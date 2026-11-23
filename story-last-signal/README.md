# StoryLastSignal - Sinyal Terakhir
TAHAP PEMASANGAN (tools + aset + dokumen skill).
Pipeline video pendek tentang sinyal terakhir Cassini.
## Ringkasan pipeline
1. Director contract (JSON): shotlist, kamera, durasi, narasi.
2. Render 3D Python + Mesa/EGL surfaceless (llvmpipe): frame PNG.
3. Audio prosedural (SoX/Python): wav, loudnorm two-pass -14 LUFS.
4. Overlay Remotion (StoryLastSignal.tsx): teks + grafis.
5. GitHub Actions matrix: render paralel per chunk/shard.
## Pola skill
- Director-contract JSON adalah single source of truth.
- Disiplin frame: semua visual murni fungsi frame.
- Tanpa Date.now / random tanpa seed.
- Loudnorm two-pass ke -14 LUFS.
- Offline-first: salin file lokal ke folder scene.
- Grep CDN harus kosong sebelum render.
- Render berat: checkpoint per frame + chunk <40 menit + tmux.
- Jangan simpan PNG sequence + shard all-intra sekaligus.
## Lingkungan (terpasang 2026-11-23)
- Ubuntu 24.04.5 LTS, Python 3.12.3, ffmpeg 6.1.1, SoX 14.4.2.
- Venv: ~/story-venv, pip 26.3, PyOpenGL 3.1.10, numpy 2.5.5.
- DracoPy 2.2.0, Pillow 13.0.0, PyOpenGL_accelerate 3.1.10.
- EGL surfaceless + llvmpipe (LLVM 20.1.2) terverifikasi.
- Mesin: cs-922182540616-default, gcloud project tetap unset.
## Aset (publik, 2048x1024 kecuali GLB)
- cassini-huygens-a.glb, 1660492 byte, NASA public domain.
- earth-day-2k.jpg 147K, earth-night-2k.jpg 112K, NASA via three.js.
- earth-clouds-2k.jpg 944K, 2048x1024, Solar System Scope.
- earth-normal-2k.jpg 329K, earth-specular-2k.jpg 219K.
- milky-way-eso-2k.jpg 211K, ESO eso0932a, CC BY 4.0.
## Catatan unduhan yang gagal
- eoimages.gsfc.nasa.gov: timeout 30 dtk, RC 28, 0 byte.
- Solar System Scope normal/specular: 404, HTML 16168 byte.
- Normal/specular pengganti: three.js earth_normal/specular_2048.
## Status: file pipeline BELUM ditulis
- story-shotlist.json, prepare_story_assets.py, render_story_3d.py
- generate-story-audio.py, StoryLastSignal.tsx, render-story.yml
- Keenam file di atas BELUM ditulis, masih harus dibangun dari spek.
- JANGAN render 600 frame / video apa pun pada tahap ini.

## Tahap 2 — StoryLastSignal (2026-11-23)
- Pipeline: scripts/director/story-shotlist.json, scripts/prepare_story_assets.py,
  scripts/render_story_3d.py, scripts/generate-story-audio.py,
  src/StoryLastSignal.tsx (+ src/lib/directorShotlist.ts, src/schemaStory.ts,
  src/Root.tsx), .github/workflows/render-story.yml.
- PENGECUALIAN FONT: proyek ini mengunci Outfit (@fontsource/outfit);
  komposisi StoryLastSignal memakai Inter & Plus Jakarta Sans.
- Nilai eye/target/roll/sunDirection/probeCenter TIDAK ada di spek: dipakai
  default turunan, ditandai "derived": true di story-shotlist.json.
- Cassini sebenarnya: 25.736 segitiga (klaim spek 25.724), 77.208 vertex flat,
  26.647 vertex unik; cache cassini_cache.npz 410.168 byte.
- Render Cloud Shell: konteks desktop GL 3.3 tidak tersedia (Mesa 25.2.8
  surfaceless hanya memberi OpenGL ES 3.2 llvmpipe); render_story_3d.py
  mencoba GL 3.3 dulu, lalu fallback ke GLES 300 es di mesin ini.
  Di GitHub Actions (ubuntu-latest, Mesa llvmpipe) dipakai GL 330 core
  sesuai spek. Smoke test frame 0: 3,91 dtk; frame 320 (Act 3): 3,19 dtk.
- Audio akhir: public/sfx/last-signal.wav, 20,00 dtk, 48 kHz stereo,
  terukur I=-13,75 LUFS, TP=-1,02 dBTP, LRA=4,20 (target -14,0 / -1,0 / 9,0).
- Aset: hanya 6 tekstur 2048x1024 yang ada (bukan 7): earth-day, earth-night,
  earth-clouds, earth-normal, earth-specular, milky-way-eso-2k.
