#!/usr/bin/env python3
"""StoryLastSignal Tahap 2 - render_story_3d.py
Render 3D OpenGL (PyOpenGL, EGL surfaceless Mesa) 1080x1920 @30fps.
3 pass per frame: (1) HDR scene RGBA16F+depth24, (2) bloom quarter-res
threshold 0.88 + Gaussian separable + anamorphic streak, (3) composite
DoF 8-tap, chromatic aberration, ACES, gamma 2.2, vignette, grain.
Semua pose/kamera murni fungsi frame (tanpa Date.now / random tanpa seed).
CLI: --frame N | --start A --end B [--out DIR] [--video FILE]
Checkpoint per frame di <out>/.checkpoint agar resume aman.
"""
import argparse, ctypes, json, math, os, subprocess, sys, time
from pathlib import Path
import numpy as np
from PIL import Image

os.environ.setdefault("EGL_PLATFORM", "surfaceless")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")  # PyOpenGL harus deteksi konteks EGL, bukan GLX
ROOT = Path(__file__).resolve().parent.parent
W, H, FPS = 1080, 1920, 30
EARTH_CENTER = np.array([28.0, 4.0, -52.0], dtype=np.float64)
EARTH_RADIUS = 17.5

# ---------- EGL surfaceless (ctypes; PyOpenGL EGL butuh arg out eksplisit) ----------
def init_egl():
    lib = ctypes.CDLL("libEGL.so.1")
    lib.eglGetPlatformDisplay.restype = ctypes.c_void_p
    lib.eglGetPlatformDisplay.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
    lib.eglInitialize.restype = ctypes.c_int
    lib.eglInitialize.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.eglBindAPI.restype = ctypes.c_int
    lib.eglChooseConfig.restype = ctypes.c_int
    lib.eglCreateContext.restype = ctypes.c_void_p
    lib.eglCreatePbufferSurface.restype = ctypes.c_void_p
    lib.eglMakeCurrent.restype = ctypes.c_int
    disp = lib.eglGetPlatformDisplay(0x31DD, None, None)  # EGL_PLATFORM_SURFACELESS_MESA
    if not disp:
        disp = lib.eglGetDisplay(0)
    maj, minor = ctypes.c_int(), ctypes.c_int()
    if not lib.eglInitialize(disp, ctypes.byref(maj), ctypes.byref(minor)):
        raise RuntimeError("eglInitialize gagal")
    lib.eglBindAPI(0x30A0)  # EGL_OPENGL_API
    att = (ctypes.c_int * 15)(0x3033, 0x0001, 0x3040, 0x0008, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8, 0x3025, 24, 0x3038)
    cfg = (ctypes.c_void_p * 1)(); num = ctypes.c_int()
    if not lib.eglChooseConfig(disp, att, cfg, 1, ctypes.byref(num)) or num.value < 1:
        raise RuntimeError("eglChooseConfig gagal")
    ctx = None
    for majv, minv in ((3, 3), (3, 2), (3, 0)):
        catt = (ctypes.c_int * 5)(0x3098, majv, 0x30FB, minv, 0x3038)
        ctx = lib.eglCreateContext(disp, cfg[0], None, catt)
        if ctx:
            break
    if not ctx:
        lib.eglBindAPI(0x30A1)
        for majv, minv in ((3, 2), (3, 0)):
            catt = (ctypes.c_int * 5)(0x3098, majv, 0x30FB, minv, 0x3038)
            ctx = lib.eglCreateContext(disp, cfg[0], None, catt)
            if ctx:
                break
    if not ctx:
        raise RuntimeError("eglCreateContext gagal (semua versi)")
    satt = (ctypes.c_int * 5)(0x3057, W, 0x3056, H, 0x3038)  # pbuffer harus sebesar frame, bukan 64x64
    surf = lib.eglCreatePbufferSurface(disp, cfg[0], satt)
    if not lib.eglMakeCurrent(disp, surf, surf, ctx):
        raise RuntimeError("eglMakeCurrent gagal")
    return lib, disp, ctx, surf

# ---------- math ----------
def normalize(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v

def look_at(eye, target, up=(0.0, 1.0, 0.0)):
    f = normalize(np.array(target, dtype=np.float64) - np.array(eye, dtype=np.float64))
    r = normalize(np.cross(f, np.array(up, dtype=np.float64)))
    u = np.cross(r, f)
    m = np.eye(4, dtype=np.float32)
    m[0, :3], m[1, :3], m[2, :3] = r, u, -f
    m[0, 3], m[1, 3], m[2, 3] = -np.dot(r, eye), -np.dot(u, eye), np.dot(f, eye)
    return m

def perspective(fov_y_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fov_y_deg) / 2.0)
    m = np.zeros((4, 4), dtype=np.float32)
    m[0, 0], m[1, 1] = f / aspect, f
    m[2, 2], m[2, 3] = (far + near) / (near - far), 2 * far * near / (near - far)
    m[3, 2] = -1.0
    return m

def rot_x(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]], dtype=np.float32)

def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=np.float32)

def translate(v):
    m = np.eye(4, dtype=np.float32); m[:3, 3] = v; return m

def scale_mat(s):
    m = np.eye(4, dtype=np.float32); m[0, 0], m[1, 1], m[2, 2] = s, s, s; return m

def lerp(a, b, t):
    return np.array(a, dtype=np.float64) * (1 - t) + np.array(b, dtype=np.float64) * t

def hash1(n):
    return float(abs(math.sin(n * 12.9898) * 43758.5453) % 1.0)

# ---------- GL helpers (import setelah EGL aktif di main, tapi nama di-resolve saat dipakai) ----------
from OpenGL.GL import (glGenVertexArrays, glBindVertexArray, glGenBuffers, glBindBuffer,
    glBufferData, glEnableVertexAttribArray, glVertexAttribPointer, glGenTextures,
    glBindTexture, glTexImage2D, glTexParameteri, glGenerateMipmap, glGenFramebuffers,
    glBindFramebuffer, glFramebufferTexture2D, glCheckFramebufferStatus, glViewport,
    glClearColor, glClear, glUseProgram, glGetUniformLocation, glUniform1i, glUniform1f,
    glUniform3f, glUniformMatrix4fv, glDrawArrays, glDrawElements, glEnable, glDisable,
    glBlendFunc, glDepthMask, glReadPixels, glGetString, glCreateShader, glShaderSource,
    glCompileShader, glGetShaderiv, glGetShaderInfoLog, glCreateProgram, glAttachShader,
    glLinkProgram, glGetProgramiv, glGetProgramInfoLog, glDeleteShader,
    GL_VERTEX_SHADER, GL_FRAGMENT_SHADER, GL_COMPILE_STATUS, GL_LINK_STATUS,
    GL_ARRAY_BUFFER, GL_ELEMENT_ARRAY_BUFFER, GL_STATIC_DRAW, GL_FLOAT, GL_UNSIGNED_INT,
    GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER, GL_TEXTURE_WRAP_S,
    GL_TEXTURE_WRAP_T, GL_LINEAR, GL_LINEAR_MIPMAP_LINEAR, GL_REPEAT, GL_CLAMP_TO_EDGE,
    GL_RGB, GL_RGBA, GL_RGBA16F, GL_DEPTH_COMPONENT24, GL_UNSIGNED_BYTE,
    GL_COLOR_ATTACHMENT0, GL_DEPTH_ATTACHMENT, GL_FRAMEBUFFER, GL_FRAMEBUFFER_COMPLETE,
    GL_COLOR_BUFFER_BIT, GL_DEPTH_BUFFER_BIT, GL_TRIANGLES, GL_POINTS, GL_DEPTH_TEST,
    GL_BLEND, GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_CULL_FACE, GL_BACK,
    GL_VERSION, GL_TRIANGLE_STRIP, GL_TRUE)

def compile_program(vs_src, fs_src):
    def sh(kind, src):
        s = glCreateShader(kind)
        glShaderSource(s, src)
        glCompileShader(s)
        if not glGetShaderiv(s, GL_COMPILE_STATUS):
            raise RuntimeError("shader gagal: " + str(glGetShaderInfoLog(s)))
        return s
    vs, fs = sh(GL_VERTEX_SHADER, vs_src), sh(GL_FRAGMENT_SHADER, fs_src)
    prog = glCreateProgram()
    glAttachShader(prog, vs); glAttachShader(prog, fs); glLinkProgram(prog)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        raise RuntimeError("link gagal: " + str(glGetProgramInfoLog(prog)))
    glDeleteShader(vs); glDeleteShader(fs)
    return prog

def make_vao(verts, indices=None, stride=8):
    vao = glGenVertexArrays(1); glBindVertexArray(vao)
    vbo = glGenBuffers(1); glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferData(GL_ARRAY_BUFFER, verts.nbytes, verts, GL_STATIC_DRAW)
    for loc, off in ((0, 0), (1, 3), (2, 6)):
        glEnableVertexAttribArray(loc)
        glVertexAttribPointer(loc, 3 if loc < 2 else 2, GL_FLOAT, False, stride * 4, ctypes.c_void_p(off * 4))
    ebo = None
    if indices is not None:
        ebo = glGenBuffers(1); glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)
    glBindVertexArray(0)
    return vao, (len(indices) if indices is not None else len(verts))

def load_texture(path, srgb=False):
    img = Image.open(path).convert("RGB")
    img = img.transpose(Image.FLIP_TOP_BOTTOM)
    data = np.array(img, dtype=np.uint8)
    tex = glGenTextures(1); glBindTexture(GL_TEXTURE_2D, tex)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR_MIPMAP_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, data.shape[1], data.shape[0], 0, GL_RGB, GL_UNSIGNED_BYTE, data)
    glGenerateMipmap(GL_TEXTURE_2D)
    return tex

def sphere_mesh(radius, center, lat=48, lon=96):
    rows = []
    for i in range(lat + 1):
        th = math.pi * i / lat
        for j in range(lon + 1):
            ph = 2 * math.pi * j / lon
            n = np.array([math.sin(th) * math.cos(ph), math.cos(th), math.sin(th) * math.sin(ph)])
            p = center + radius * n
            rows.append([p[0], p[1], p[2], n[0], n[1], n[2], j / lon, i / lat])
    idx = []
    for i in range(lat):
        for j in range(lon):
            a, b = i * (lon + 1) + j, (i + 1) * (lon + 1) + j
            idx += [a, b, a + 1, b, b + 1, a + 1]
    return np.array(rows, dtype=np.float32), np.array(idx, dtype=np.uint32)

def cone_mesh(r0, r1, length, seg=32):
    rows = []
    for i in range(seg + 1):
        a = 2 * math.pi * i / seg
        for (r, z) in ((r0, 0.0), (r1, length)):
            rows.append([r * math.cos(a), r * math.sin(a), z, math.cos(a), math.sin(a), 0.0, i / seg, z / length])
    idx = []
    for i in range(seg):
        a, b = i * 2, i * 2 + 2
        idx += [a, b, a + 1, b, b + 1, a + 1]
    return np.array(rows, dtype=np.float32), np.array(idx, dtype=np.uint32)

def ring_mesh(r_in, r_out, seg=64):
    rows = []
    for i in range(seg + 1):
        a = 2 * math.pi * i / seg
        for r in (r_in, r_out):
            rows.append([r * math.cos(a), r * math.sin(a), 0.0, 0.0, 0.0, 1.0, i / seg, r])
    idx = []
    for i in range(seg):
        a, b = i * 2, i * 2 + 2
        idx += [a, b, a + 1, b, b + 1, a + 1]
    return np.array(rows, dtype=np.float32), np.array(idx, dtype=np.uint32)

# ---------- Shaders ----------
VS_SCENE = """
#version 330 core
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aNrm; layout(location=2) in vec2 aUV;
uniform mat4 uMVP; uniform mat4 uModel; uniform mat3 uNrm;
out vec3 vNrm; out vec3 vWorld; out vec2 vUV;
void main(){ vec4 w = uModel * vec4(aPos,1.0); vWorld = w.xyz; vNrm = uNrm * aNrm; vUV = aUV;
  gl_Position = uMVP * vec4(aPos,1.0); }
"""
FS_SCENE = """
#version 330 core
in vec3 vNrm; in vec3 vWorld; in vec2 vUV; out vec4 FragColor;
uniform vec3 uSun; uniform vec3 uCam; uniform vec3 uEarthC; uniform float uEarthR;
uniform int uKind; uniform sampler2D uDay; uniform sampler2D uNight; uniform sampler2D uCloud;
uniform vec3 uBase; uniform float uTime; uniform float uGlow; uniform float uAct;
void main(){
  vec3 N = normalize(vNrm); vec3 L = normalize(uSun); vec3 V = normalize(uCam - vWorld);
  float diff = max(dot(N, L), 0.0);
  vec3 col;
  if (uKind == 1) { // Bumi: day + night + clouds + specular
    vec2 uv2 = vec2(vUV.x + uTime * 0.004, vUV.y);
    vec3 day = texture(uDay, vUV).rgb; vec3 night = texture(uNight, vUV).rgb;
    vec3 cl = texture(uCloud, uv2).rgb;
    float city = smoothstep(0.25, 0.9, night.r) * max(0.0, -dot(N, L));
    vec3 H = normalize(L + V); float spec = pow(max(dot(N, H), 0.0), 32.0) * 0.6;
    col = day * (0.08 + diff) + night * city * 2.0 + cl * (0.15 + diff * 0.7) + vec3(spec);
    if (uAct >= 3.5) col += vec3(0.0, 0.25, 0.35) * max(0.0, dot(N, normalize(uEarthC - vWorld))) * 0.6; // aurora Act 4
  } else if (uKind == 2) { // halo Rayleigh Fresnel (bola luar, back-face)
    float fr = pow(1.0 - abs(dot(N, V)), 2.5);
    col = vec3(0.22, 0.74, 0.97) * fr * 1.4; FragColor = vec4(col, fr); return;
  } else { // Cassini PBR sederhana + earthshine + dish glow
    vec3 earthDir = normalize(uEarthC - vWorld);
    float earth = max(dot(N, earthDir), 0.0) * 0.35;
    vec3 H = normalize(L + V); float spec = pow(max(dot(N, H), 0.0), 48.0);
    col = uBase * (0.10 + diff * 1.15 + earth * vec3(0.22, 0.45, 0.75)) + vec3(1.0) * spec * 0.5;
    col += uBase * uGlow * 1.5; // dish glow / beacon
  }
  FragColor = vec4(col, 1.0);
}
"""
VS_SKY = """
#version 330 core
layout(location=0) in vec3 aPos; out vec3 vDir;
uniform mat4 uInv; void main(){ vDir = (uInv * vec4(aPos.xy, 1.0, 1.0)).xyz; gl_Position = vec4(aPos, 1.0); }
"""
FS_SKY = """
#version 330 core
in vec3 vDir; out vec4 FragColor;
uniform sampler2D uSky; uniform vec3 uSun; uniform vec3 uBg;
void main(){
  vec3 d = normalize(vDir);
  vec2 uv = vec2(atan(d.z, d.x) / 6.2831853 + 0.5, asin(clamp(d.y, -1.0, 1.0)) / 3.14159265 + 0.5);
  vec3 col = texture(uSky, uv).rgb * 0.9 + uBg * 0.4;
  float s = max(dot(d, normalize(uSun)), 0.0);
  col += vec3(1.0, 0.95, 0.85) * pow(s, 900.0) * 6.0;   // sun disc
  col += vec3(1.0, 0.9, 0.7) * pow(s, 18.0) * 0.35;     // korona
  FragColor = vec4(col, 1.0);
}
"""
VS_POINTS = """
#version 330 core
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aNrm; layout(location=2) in vec2 aUV;
uniform mat4 uMVP; uniform float uSize; out float vTw; out vec3 vCol;
void main(){ gl_Position = uMVP * vec4(aPos, 1.0);
  float tw = 0.75 + 0.25 * sin(aUV.x * 40.0 + aUV.y * 7.0);
  gl_PointSize = uSize * tw / max(1.0, -gl_Position.z * 0.05);
  vTw = tw; vCol = vec3(aNrm); }
"""
FS_POINTS = """
#version 330 core
in float vTw; in vec3 vCol; out vec4 FragColor;
void main(){ vec2 c = gl_PointCoord - 0.5; float d = length(c);
  float a = smoothstep(0.5, 0.05, d) * vTw; FragColor = vec4(vCol * a * 1.6, a); }
"""
VS_QUAD = """
#version 330 core
layout(location=0) in vec3 aPos; layout(location=1) in vec3 aNrm; layout(location=2) in vec2 aUV;
out vec2 vUV; void main(){ vUV = aUV; gl_Position = vec4(aPos.xy, 0.0, 1.0); }
"""
FS_BLOOM = """
#version 330 core
in vec2 vUV; out vec4 FragColor;
uniform sampler2D uTex; uniform vec2 uDir; uniform float uThresh; uniform float uStretch;
void main(){
  vec3 c = texture(uTex, vUV).rgb;
  if (uThresh > 0.0) { float l = dot(c, vec3(0.2126, 0.7152, 0.0722)); c *= smoothstep(uThresh, uThresh + 0.12, l); }
  vec3 acc = c * 0.227027; vec2 off = uDir * uStretch / vec2(1080.0, 1920.0) * 4.0;
  float w[4] = float[4](0.1945946, 0.1216216, 0.054054, 0.016216);
  for (int i = 1; i <= 4; i++) { acc += texture(uTex, vUV + off * float(i)).rgb * w[i-1];
    acc += texture(uTex, vUV - off * float(i)).rgb * w[i-1]; }
  FragColor = vec4(acc, 1.0);
}
"""
FS_COMP = """
#version 330 core
in vec2 vUV; out vec4 FragColor;
uniform sampler2D uScene; uniform sampler2D uBloom; uniform sampler2D uDepth;
uniform float uFocus; uniform float uDof; uniform float uBloomBoost; uniform float uFrame;
uniform vec2 uRes;
float depthAt(vec2 uv){ float d = texture(uDepth, uv).r; return 1.0 / (d * 98.0 + 0.02); }
void main(){
  vec2 uv = vUV; vec2 cen = uv - 0.5; float r = length(cen);
  float ca = r * r * 0.012;
  vec3 col;
  float focus = uFocus; float dep = depthAt(uv);
  float blurAmt = clamp(abs(dep - focus) * 0.02 * uDof, 0.0, 0.02);
  vec2 o[8] = vec2[8](vec2(1,0), vec2(-1,0), vec2(0,1), vec2(0,-1), vec2(0.7,0.7), vec2(-0.7,0.7), vec2(0.7,-0.7), vec2(-0.7,-0.7));
  vec3 acc = vec3(0.0);
  for (int i = 0; i < 8; i++) {
    vec2 s = uv + o[i] * blurAmt;
    acc += vec3(texture(uScene, s + cen * ca).r, texture(uScene, s).g, texture(uScene, s - cen * ca).b);
  }
  col = acc / 8.0;
  col += texture(uBloom, uv).rgb * 0.55 * uBloomBoost;
  col = max(col, 0.0);
  col = (col * (2.51 * col + 0.03)) / (col * (2.43 * col + 0.59) + 0.14); // ACES filmic
  col = pow(col, vec3(1.0 / 2.2));
  col *= 1.0 - 0.35 * r * r; // vignette
  float g = fract(sin(dot(uv * (uFrame + 1.0), vec2(12.9898, 78.233))) * 43758.5453);
  col += (g - 0.5) * 0.02; // film grain
  FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""

# ---------- Renderer ----------
MAT_COLORS = [(0.96, 0.62, 0.04), (0.75, 0.78, 0.82), (0.12, 0.13, 0.16), (0.90, 0.90, 0.92),
              (0.72, 0.35, 0.18), (0.85, 0.68, 0.20), (0.05, 0.06, 0.08), (0.95, 0.95, 0.97)]
BEACON = {1: (0.22, 0.74, 0.97), 2: (0.22, 0.74, 0.97), 3: (0.96, 0.62, 0.04), 4: (0.96, 0.62, 0.04)}

class Renderer:
    def __init__(self, shotlist):
        self.shots = shotlist["shots"]
        self.sun = normalize(shotlist["world"].get("sunDirection", [-0.6, 0.35, 0.72]))
        init_egl()
        from OpenGL.GL import glGetString as _gs
        ver_str = _gs(GL_VERSION)
        print("GL:", ver_str)
        self.es = bool(ver_str and ver_str.startswith(b"OpenGL ES"))
        hdr = "#version 300 es" + chr(10) + "precision highp float;" + chr(10) + "precision highp int;" + chr(10) + "precision mediump sampler2D;" if self.es else "#version 330 core"
        print("mode shader:", "GLES 300 es (fallback Cloud Shell)" if self.es else "GL 330 core (sesuai spek)")
        def _h(src):
            return src.replace("#version 330 core", hdr, 1)
        glEnable(GL_DEPTH_TEST)
        self.prog_scene = compile_program(_h(VS_SCENE), _h(FS_SCENE))
        self.prog_sky = compile_program(_h(VS_SKY), _h(FS_SKY))
        self.prog_points = compile_program(_h(VS_POINTS), _h(FS_POINTS))
        self.prog_bloom = compile_program(_h(VS_QUAD), _h(FS_BLOOM))
        self.prog_comp = compile_program(_h(VS_QUAD), _h(FS_COMP))
        self._load_textures()
        self._build_geometry()
        self._build_fbos()

    def _tex_or(self, name, fallback):
        p = ROOT / "assets" / "textures" / name
        if p.exists():
            try:
                return load_texture(p)
            except Exception as e:
                print("tekstur gagal, pakai fallback:", name, e)
        img = Image.new("RGB", (8, 8), fallback)
        arr = np.array(img, dtype=np.uint8)
        tex = glGenTextures(1); glBindTexture(GL_TEXTURE_2D, tex)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, 8, 8, 0, GL_RGB, GL_UNSIGNED_BYTE, arr)
        return tex

    def _load_textures(self):
        self.tex_day = self._tex_or("earth-day-2k.jpg", (40, 90, 140))
        self.tex_night = self._tex_or("earth-night-2k.jpg", (5, 5, 10))
        self.tex_cloud = self._tex_or("earth-clouds-2k.jpg", (200, 200, 200))
        self.tex_sky = self._tex_or("milky-way-eso-2k.jpg", (5, 8, 20))

    def _build_geometry(self):
        quad = np.array([[-1, -1, 0, 0, 0, 1, 0, 0], [3, -1, 0, 0, 0, 1, 2, 0],
                         [-1, 3, 0, 0, 0, 1, 0, 2]], dtype=np.float32)
        self.quad_vao, self.quad_n = make_vao(quad)
        ev, ei = sphere_mesh(EARTH_RADIUS, EARTH_CENTER)
        self.earth_vao, self.earth_n = make_vao(ev, ei)
        hv, hi = sphere_mesh(EARTH_RADIUS * 1.06, EARTH_CENTER)
        self.halo_vao, self.halo_n = make_vao(hv, hi)
        rng = np.random.default_rng(1234)
        pts = []
        for i in range(1600):
            if i < 300:
                p = rng.normal(0, 1, 3); p = p / np.linalg.norm(p) * rng.uniform(2.0, 9.0)
                col = (0.8, 0.85, 0.9)
            else:
                p = rng.normal(0, 1, 3); p = p / np.linalg.norm(p) * rng.uniform(70.0, 120.0)
                b = rng.uniform(0.5, 1.0)
                col = (b, b * rng.uniform(0.85, 1.0), b * rng.uniform(0.8, 1.0))
            pts.append([p[0], p[1], p[2], col[0], col[1], col[2], hash1(i), hash1(i + 5000)])
        self.pts_vao, self.pts_n = make_vao(np.array(pts, dtype=np.float32))
        cache = np.load(ROOT / "assets" / "cache" / "cassini_cache.npz")
        verts = cache["vertices"].astype(np.float32)
        mats = cache["triangle_material"]
        self.cassini = []
        per_vert_mat = np.repeat(mats, 3)
        for mid in sorted(set(int(m) for m in mats)):
            sel = verts[per_vert_mat == mid]
            if len(sel):
                vao, n = make_vao(sel)
                self.cassini.append((vao, n, MAT_COLORS[mid % len(MAT_COLORS)]))
        print("Cassini VAO: material", len(self.cassini), "vertex", len(verts))
        cv, ci = cone_mesh(0.15, 2.5, 45.0)
        self.beam_vao, self.beam_n = make_vao(cv, ci)
        rv, ri = ring_mesh(0.85, 1.0)
        self.ring_vao, self.ring_n = make_vao(rv, ri)
        sv, si = sphere_mesh(0.4, np.array([0.0, 3.0, 0.0]))
        self.beacon_vao, self.beacon_n = make_vao(sv, si)

    def _fbo(self, w, h, depth=False):
        fbo = glGenFramebuffers(1); glBindFramebuffer(GL_FRAMEBUFFER, fbo)
        tex = glGenTextures(1); glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA16F, w, h, 0, GL_RGBA, GL_FLOAT, None)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0)
        dtex = None
        if depth:
            dtex = glGenTextures(1); glBindTexture(GL_TEXTURE_2D, dtex)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT24, w, h, 0, 0x1902, GL_UNSIGNED_INT, None)
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, dtex, 0)
        if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("FBO tidak lengkap")
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        return fbo, tex, dtex

    def _build_fbos(self):
        self.fbo_scene, self.tex_scene, self.tex_depth = self._fbo(W, H, depth=True)
        self.fbo_bloom, self.tex_bloom, _ = self._fbo(W // 4, H // 4)
        self.fbo_blur, self.tex_blur, _ = self._fbo(W // 4, H // 4)

    def shot_for(self, frame):
        for s in self.shots:
            if s["startFrame"] <= frame <= s["endFrame"]:
                return s
        return self.shots[-1]

    def camera(self, frame, shot):
        n = max(1, shot["endFrame"] - shot["startFrame"])
        t = (frame - shot["startFrame"]) / n
        t = t * t * (3 - 2 * t)  # smoothstep
        eye = lerp(shot["eyeStart"], shot["eyeEnd"], t)
        tgt = lerp(shot["targetStart"], shot["targetEnd"], t)
        if shot.get("shake", 0):
            sh = shot["shake"]
            eye = eye + np.array([math.sin(frame * 1.7) * 0.12, math.sin(frame * 2.3 + 1.0) * 0.09,
                                  math.sin(frame * 1.3 + 2.0) * 0.12]) * sh
        roll = math.radians(lerp(shot["rollStartDeg"], shot["rollEndDeg"], t))
        fov = 2 * math.degrees(math.atan(12.0 / shot["lensMm"]))
        return eye, tgt, roll, fov, lerp(shot["focusDistStart"], shot["focusDistEnd"], t)

from OpenGL.GL import (glUniformMatrix3fv as _u3, glUniform2f as _u2,
    glActiveTexture as _act, GL_TEXTURE0 as _T0, GL_TEXTURE1 as _T1, GL_TEXTURE2 as _T2)

def _set_scene(r, prog, mvp, model, kind, base, glow, act, tsec, eye):
    glUseProgram(prog)
    glUniformMatrix4fv(glGetUniformLocation(prog, "uMVP"), 1, GL_TRUE, mvp.astype(np.float32))
    glUniformMatrix4fv(glGetUniformLocation(prog, "uModel"), 1, GL_TRUE, model.astype(np.float32))
    _u3(glGetUniformLocation(prog, "uNrm"), 1, GL_TRUE, model[:3, :3].astype(np.float32))
    glUniform3f(glGetUniformLocation(prog, "uSun"), float(r.sun[0]), float(r.sun[1]), float(r.sun[2]))
    glUniform3f(glGetUniformLocation(prog, "uCam"), float(eye[0]), float(eye[1]), float(eye[2]))
    glUniform3f(glGetUniformLocation(prog, "uEarthC"), float(EARTH_CENTER[0]), float(EARTH_CENTER[1]), float(EARTH_CENTER[2]))
    glUniform1f(glGetUniformLocation(prog, "uEarthR"), float(EARTH_RADIUS))
    glUniform1i(glGetUniformLocation(prog, "uKind"), int(kind))
    glUniform3f(glGetUniformLocation(prog, "uBase"), float(base[0]), float(base[1]), float(base[2]))
    glUniform1f(glGetUniformLocation(prog, "uTime"), float(tsec))
    glUniform1f(glGetUniformLocation(prog, "uGlow"), float(glow))
    glUniform1f(glGetUniformLocation(prog, "uAct"), float(act))

def _bind_tex(unit, tex):
    _act(unit); glBindTexture(GL_TEXTURE_2D, tex)

def _draw(vao, n, indexed=True):
    glBindVertexArray(vao)
    if indexed:
        glDrawElements(GL_TRIANGLES, n, GL_UNSIGNED_INT, None)
    else:
        glDrawArrays(GL_TRIANGLES, 0, n)
    glBindVertexArray(0)

def render_frame(r, frame):
    shot = r.shot_for(frame)
    act = shot["act"]
    eye, tgt, roll, fov, focus = r.camera(frame, shot)
    tsec = frame / FPS
    view = look_at(eye, tgt) @ rot_z(roll)
    proj = perspective(fov, W / H, 0.1, 500.0)
    # PASS 1: HDR scene
    glBindFramebuffer(GL_FRAMEBUFFER, r.fbo_scene)
    glViewport(0, 0, W, H)
    glClearColor(0.0196, 0.0314, 0.0784, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glDisable(GL_DEPTH_TEST); glDepthMask(False)
    glUseProgram(r.prog_sky)
    view_rot = view.copy(); view_rot[0, 3] = view_rot[1, 3] = view_rot[2, 3] = 0.0
    inv = np.linalg.inv(proj @ view_rot).astype(np.float32)
    glUniformMatrix4fv(glGetUniformLocation(r.prog_sky, "uInv"), 1, GL_TRUE, inv)
    glUniform3f(glGetUniformLocation(r.prog_sky, "uSun"), float(r.sun[0]), float(r.sun[1]), float(r.sun[2]))
    glUniform3f(glGetUniformLocation(r.prog_sky, "uBg"), 0.0196, 0.0314, 0.0784)
    _bind_tex(_T0, r.tex_sky); glUniform1i(glGetUniformLocation(r.prog_sky, "uSky"), 0)
    _draw(r.quad_vao, r.quad_n, indexed=False)
    glEnable(GL_DEPTH_TEST); glDepthMask(True)
    # point sprites: 300 debu dekat + 1300 bintang jauh
    glUseProgram(r.prog_points)
    glUniformMatrix4fv(glGetUniformLocation(r.prog_points, "uMVP"), 1, GL_TRUE, (proj @ view).astype(np.float32))
    glUniform1f(glGetUniformLocation(r.prog_points, "uSize"), 90.0)
    glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE); glDepthMask(False)
    _draw(r.pts_vao, r.pts_n, indexed=False)
    glDepthMask(True); glDisable(GL_BLEND)
    _bind_tex(_T0, r.tex_day); _bind_tex(_T1, r.tex_night); _bind_tex(_T2, r.tex_cloud)
    glUseProgram(r.prog_scene)
    glUniform1i(glGetUniformLocation(r.prog_scene, "uDay"), 0)
    glUniform1i(glGetUniformLocation(r.prog_scene, "uNight"), 1)
    glUniform1i(glGetUniformLocation(r.prog_scene, "uCloud"), 2)
    ident = np.eye(4, dtype=np.float32)
    _set_scene(r, r.prog_scene, proj @ view, ident, 1, (1, 1, 1), 0.0, act, tsec, eye)
    _draw(r.earth_vao, r.earth_n)
    glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE); glDepthMask(False)
    _set_scene(r, r.prog_scene, proj @ view, ident, 2, (1, 1, 1), 0.0, act, tsec, eye)
    _draw(r.halo_vao, r.halo_n)
    glDepthMask(True); glDisable(GL_BLEND)
    for vao, n, col in r.cassini:
        glow = 0.9 if (act >= 3 and col == MAT_COLORS[0]) else 0.0
        _set_scene(r, r.prog_scene, proj @ view, ident, 0, col, glow, act, tsec, eye)
        _draw(vao, n, indexed=False)
    # beam VFX: kerucut beam + cincin
    beam_dir = normalize(EARTH_CENTER)
    bx = normalize(np.cross([0, 1, 0], beam_dir)); by = np.cross(beam_dir, bx)
    basis = np.eye(4, dtype=np.float32)
    basis[:3, 0], basis[:3, 1], basis[:3, 2] = bx, by, beam_dir
    if act >= 3:
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE); glDepthMask(False)
        _set_scene(r, r.prog_scene, proj @ view @ basis, basis, 0, (0.96, 0.62, 0.04), 0.8, act, tsec, eye)
        _draw(r.beam_vao, r.beam_n)
        for i in range(9):
            tt = (i + 0.5) / 9.0
            pos = beam_dir * (4.0 + tt * 38.0)
            m = translate(pos) @ basis @ scale_mat(0.4 + tt * 2.0)
            _set_scene(r, r.prog_scene, proj @ view @ m, m, 0, (0.96, 0.62, 0.04), 1.0, act, tsec, eye)
            _draw(r.ring_vao, r.ring_n)
        glDepthMask(True); glDisable(GL_BLEND)
    if act == 2:
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE); glDepthMask(False)
        for k in range(3):
            rr = 2.0 + ((frame * 0.35 + k * 4.0) % 12.0)
            m = rot_x(math.pi / 2) @ scale_mat(rr)
            _set_scene(r, r.prog_scene, proj @ view @ m, m, 0, (0.22, 0.74, 0.97), 0.7, act, tsec, eye)
            _draw(r.ring_vao, r.ring_n)
        for j, off in enumerate([(1.5, 0.5, 0), (-1.5, 0.5, 0), (0.5, -1.5, 0), (-0.5, 1.5, 0)]):
            if frame % 20 < 6:
                m = translate(off) @ scale_mat(0.5)
                _set_scene(r, r.prog_scene, proj @ view @ m, m, 0, (0.22, 0.74, 0.97), 0.9, act, tsec, eye)
                _draw(r.beam_vao, r.beam_n)
        glDepthMask(True); glDisable(GL_BLEND)
    _set_scene(r, r.prog_scene, proj @ view, ident, 0, BEACON[act], 1.2, act, tsec, eye)
    _draw(r.beacon_vao, r.beacon_n)
    # PASS 2: bloom quarter-res
    def bloom_pass(src_fbo, src_tex, dst_fbo, dx, dy, thresh, stretch):
        glBindFramebuffer(GL_FRAMEBUFFER, dst_fbo)
        glViewport(0, 0, W // 4, H // 4)
        glDisable(GL_DEPTH_TEST)
        glUseProgram(r.prog_bloom)
        _bind_tex(_T0, src_tex); glUniform1i(glGetUniformLocation(r.prog_bloom, "uTex"), 0)
        _u2(glGetUniformLocation(r.prog_bloom, "uDir"), float(dx), float(dy))
        glUniform1f(glGetUniformLocation(r.prog_bloom, "uThresh"), float(thresh))
        glUniform1f(glGetUniformLocation(r.prog_bloom, "uStretch"), float(stretch))
        _draw(r.quad_vao, r.quad_n, indexed=False)
        glEnable(GL_DEPTH_TEST)
    bloom_pass(r.fbo_scene, r.tex_scene, r.fbo_bloom, 0, 0, 0.88, 1.0)
    bloom_pass(r.fbo_bloom, r.tex_bloom, r.fbo_blur, 1, 0, 0.0, 7.5)
    bloom_pass(r.fbo_blur, r.tex_blur, r.fbo_bloom, 1, 0, 0.0, 13.0)
    # PASS 3: composite
    glBindFramebuffer(GL_FRAMEBUFFER, 0)
    glViewport(0, 0, W, H)
    glDisable(GL_DEPTH_TEST)
    glUseProgram(r.prog_comp)
    _bind_tex(_T0, r.tex_scene); _bind_tex(_T1, r.tex_bloom); _bind_tex(_T2, r.tex_depth)
    glUniform1i(glGetUniformLocation(r.prog_comp, "uScene"), 0)
    glUniform1i(glGetUniformLocation(r.prog_comp, "uBloom"), 1)
    glUniform1i(glGetUniformLocation(r.prog_comp, "uDepth"), 2)
    glUniform1f(glGetUniformLocation(r.prog_comp, "uFocus"), float(focus))
    glUniform1f(glGetUniformLocation(r.prog_comp, "uDof"), float(shot["dofStrength"]))
    glUniform1f(glGetUniformLocation(r.prog_comp, "uBloomBoost"), float(shot["bloomBoost"]))
    glUniform1f(glGetUniformLocation(r.prog_comp, "uFrame"), float(frame))
    _u2(glGetUniformLocation(r.prog_comp, "uRes"), float(W), float(H))
    _draw(r.quad_vao, r.quad_n, indexed=False)
    glEnable(GL_DEPTH_TEST)
    px = glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE)  # ES: baca RGBA (format baca terjamin)
    arr = np.frombuffer(px, dtype=np.uint8).reshape(H, W, 4)[:, :, :3].copy()
    return np.flipud(arr)

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="Render 3D StoryLastSignal (OpenGL/EGL)")
    ap.add_argument("--frame", type=int, default=None, help="render 1 frame")
    ap.add_argument("--start", type=int, default=None, help="frame awal shard")
    ap.add_argument("--end", type=int, default=None, help="frame akhir shard (inklusif)")
    ap.add_argument("--out", default="out/frames", help="direktori frame PNG")
    ap.add_argument("--shotlist", default="scripts/director/story-shotlist.json")
    ap.add_argument("--video", default=None, help="opsional: tulis juga video mp4 via ffmpeg pipe")
    args = ap.parse_args()
    if args.frame is not None:
        frames = [args.frame]
    elif args.start is not None and args.end is not None:
        frames = list(range(args.start, args.end + 1))
    else:
        ap.error("beri --frame N atau --start A --end B")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ckpt = out / ".checkpoint"
    done = set()
    if ckpt.exists():
        done = set(int(x) for x in ckpt.read_text().split() if x.strip().isdigit())
    shotlist = json.loads(Path(args.shotlist).read_text())
    rend = Renderer(shotlist)
    ff = None
    if args.video:
        cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
               "-r", "30", "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast",
               "-crf", "10", "-g", "1", "-pix_fmt", "yuv420p", args.video]
        ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time()
    for f in frames:
        if f in done:
            print(f"frame {f}: sudah di checkpoint, dilewati")
            continue
        t1 = time.time()
        arr = render_frame(rend, f)
        Image.fromarray(arr).save(out / f"frame_{f:04d}.png")
        if ff is not None:
            ff.stdin.write(arr.tobytes())
        with open(ckpt, "a") as fh:
            fh.write(str(f) + chr(10))
        print(f"frame {f} ({rend.shot_for(f)['id']}) {time.time() - t1:.2f}s -> {out}/frame_{f:04d}.png")
    if ff is not None:
        ff.stdin.close(); ff.wait()
        print("video:", args.video, "rc", ff.returncode)
    print(f"SELESAI {len(frames)} frame dalam {time.time() - t0:.1f}s")

if __name__ == "__main__":
    main()
