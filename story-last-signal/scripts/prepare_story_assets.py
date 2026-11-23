#!/usr/bin/env python3
"""StoryLastSignal Tahap 2 - prepare_story_assets.py
Parse GLB Cassini (Draco KHR_draco_mesh_compression) secara manual:
DracoPy TIDAK parse GLB sendiri, jadi script ini parse JSON glTF +
bufferView, lalu decode tiap bufferView Draco dengan DracoPy.
Output:
  assets/textures/nasa_cassini/tex_*.png  (tekstur embed GLB)
  assets/textures/nasa_cassini/tex_01_normal.png (normal map kerutan foil Kapton)
  assets/cache/cassini_cache.npz (flat interleaved [px,py,pz,nx,ny,nz,u,v])
  assets/cache/cassini_meta.json
"""
import json, struct, sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
GLB = ROOT / "assets" / "models" / "cassini-huygens-a.glb"
TEX_DIR = ROOT / "assets" / "textures" / "nasa_cassini"
CACHE_DIR = ROOT / "assets" / "cache"
CACHE_NPZ = CACHE_DIR / "cassini_cache.npz"
META_JSON = CACHE_DIR / "cassini_meta.json"

def read_glb(path):
    data = path.read_bytes()
    if data[:4] != b"glTF":
        raise ValueError("bukan file GLB (magic glTF tidak ditemukan)")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    off = 20 + json_len
    bin_data = b""
    if off + 8 <= len(data) and data[off + 4:off + 8] == b"BIN" + chr(0).encode():
        bin_len = struct.unpack("<I", data[off:off + 4])[0]
        bin_data = data[off + 8:off + 8 + bin_len]
    return gltf, bin_data

def buffer_view_bytes(gltf, bin_data, idx):
    bv = gltf["bufferViews"][idx]
    start = bv.get("byteOffset", 0)
    return bin_data[start:start + bv["byteLength"]]

def trs_matrix(node):
    m = np.eye(4, dtype=np.float64)
    if "matrix" in node:
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    t = node.get("translation", [0, 0, 0])
    r = node.get("rotation", [0, 0, 0, 1])  # xyzw
    s = node.get("scale", [1, 1, 1])
    x, y, z, w = r
    rot = np.array([
        [1 - 2*(y*y+z*z), 2*(x*y - z*w), 2*(x*z + y*w)],
        [2*(x*y + z*w), 1 - 2*(x*x+z*z), 2*(y*z - x*w)],
        [2*(x*z - y*w), 2*(y*z + x*w), 1 - 2*(x*x+y*y)]], dtype=np.float64)
    m[:3, :3] = rot * np.array(s, dtype=np.float64)
    m[:3, 3] = t
    return m

def decode_draco(buf):
    import DracoPy
    mesh = DracoPy.decode_buffer_to_mesh(bytes(buf))
    attrs = {}
    for a in getattr(mesh, "attributes", []) or []:
        atype = a.get("attribute_type")
        data = np.asarray(a["data"], dtype=np.float32)
        attrs[int(atype)] = data
    pos = attrs.get(0)
    if pos is None:
        pos = np.asarray(mesh.points, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    nrm = attrs.get(1)
    uv = attrs.get(3)
    if nrm is None:
        nrm = np.zeros_like(pos)
    if uv is None:
        uv = np.zeros((len(pos), 2), dtype=np.float32)
    return pos, nrm, uv, faces

def extract_textures(gltf, bin_data):
    TEX_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for i, img in enumerate(gltf.get("images", [])):
        name = img.get("name") or f"tex_{i:02d}"
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        ext = {"image/png": ".png", "image/webp": ".webp", "image/jpeg": ".jpg"}.get(img.get("mimeType", ""), ".png")
        dest = TEX_DIR / f"{safe}{ext}"
        if "bufferView" in img:
            dest.write_bytes(buffer_view_bytes(gltf, bin_data, img["bufferView"]))
            out.append(str(dest))
        elif "uri" in img and not img["uri"].startswith("data:"):
            print(f"  image {i} uri eksternal, dilewati: {img['uri'][:60]}")
    return out

def kapton_normal(path, w=1024, h=512, seed=7):
    rng = np.random.default_rng(seed)
    # Kerutan foil: noise kasar di-downsample lalu di-upsample (lipatan besar),
    # ditambah noise halus (kerutan kecil). Gradien -> normal map.
    coarse = rng.normal(0, 1, (h // 16, w // 16)).astype(np.float32)
    coarse = np.array(Image.fromarray(coarse).resize((w, h), Image.BICUBIC), dtype=np.float32)
    fine = rng.normal(0, 1, (h // 4, w // 4)).astype(np.float32)
    fine = np.array(Image.fromarray(fine).resize((w, h), Image.BICUBIC), dtype=np.float32)
    height = coarse * 1.0 + fine * 0.35
    gy, gx = np.gradient(height)
    strength = 2.2
    nx = -gx * strength; ny = -gy * strength; nz = np.ones_like(height)
    norm = np.sqrt(nx*nx + ny*ny + nz*nz)
    rgb = np.stack([(nx/norm*0.5+0.5), (ny/norm*0.5+0.5), (nz/norm*0.5+0.5)], axis=-1)
    Image.fromarray((rgb * 255).astype(np.uint8)).save(path)
    return path

def main():
    gltf, bin_data = read_glb(GLB)
    print(f"GLB: {GLB} ({GLB.stat().st_size} byte)")
    print(f"meshes={len(gltf.get('meshes', []))} materials={len(gltf.get('materials', []))} images={len(gltf.get('images', []))} nodes={len(gltf.get('nodes', []))}")
    tex = extract_textures(gltf, bin_data)
    print(f"tekstur GLB diekstrak: {len(tex)}")
    for t in tex:
        print("  ", t)
    kapton = kapton_normal(TEX_DIR / "tex_01_normal.png")
    print("normal map Kapton:", kapton)
    # Traverse scene: kumpulkan (mesh, world matrix) per node.
    nodes = gltf.get("nodes", [])
    scene = gltf.get("scenes", [{}])[0]
    order = []
    def walk(idx, parent):
        node = nodes[idx]
        world = parent @ trs_matrix(node)
        if "mesh" in node:
            order.append((node["mesh"], world))
        for c in node.get("children", []):
            walk(c, world)
    for root in scene.get("nodes", []):
        walk(root, np.eye(4))
    verts, mat_ids, per_mesh = [], [], []
    total_tris = 0
    for mesh_idx, world in order:
        mesh = gltf["meshes"][mesh_idx]
        rot = world[:3, :3]
        nrot = rot / np.maximum(np.linalg.norm(rot, axis=0, keepdims=True), 1e-12)
        for prim in mesh["primitives"]:
            mat = prim.get("material", -1)
            draco = prim.get("extensions", {}).get("KHR_draco_mesh_compression", {})
            if "bufferView" not in draco:
                print(f"  LEWATI prim non-Draco mesh {mesh_idx} ({mesh.get('name')})")
                continue
            buf = buffer_view_bytes(gltf, bin_data, draco["bufferView"])
            pos, nrm, uv, faces = decode_draco(buf)
            pos_w = (rot @ pos.T).T + world[:3, 3]
            nrm_w = (nrot @ nrm.T).T
            tri = np.concatenate([pos_w, nrm_w, uv], axis=1).astype(np.float32)
            expanded = tri[faces.reshape(-1)]
            verts.append(expanded)
            mat_ids.append(np.full(len(faces), mat, dtype=np.int32))
            total_tris += len(faces)
            per_mesh.append({"mesh": mesh.get("name"), "material": mat, "triangles": int(len(faces)), "vertices": int(len(pos))})
    vertices = np.concatenate(verts, axis=0) if verts else np.zeros((0, 8), dtype=np.float32)
    tri_mats = np.concatenate(mat_ids) if mat_ids else np.zeros(0, dtype=np.int32)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE_NPZ, vertices=vertices, triangle_material=tri_mats)
    meta = {"source_glb": str(GLB), "triangles": int(total_tris), "vertices_flat": int(len(vertices)),
            "unique_vertices": int(sum(p["vertices"] for p in per_mesh)),
            "materials": gltf.get("materials", []), "per_mesh": per_mesh,
            "textures_extracted": tex, "kapton_normal": str(kapton)}
    META_JSON.write_text(json.dumps(meta, indent=2))
    print(f"SEGITIGA: {total_tris}")
    print(f"VERTEX (flat, 3 per segitiga): {len(vertices)}")
    print(f"VERTEX unik (jumlah per primitif): {meta['unique_vertices']}")
    print(f"cache: {CACHE_NPZ} ({CACHE_NPZ.stat().st_size} byte)")
    print(f"meta: {META_JSON}")

if __name__ == "__main__":
    main()
