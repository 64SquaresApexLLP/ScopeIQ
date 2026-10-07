"""Synthetic drone survey: LiDAR point cloud (LAZ), stitched imagery (JPG), orbit video (MP4), vendor measurements."""
import math, json, numpy as np, laspy, imageio.v2 as iio
from PIL import Image
import model as M

FT = M.FT
SN = M.SECT_NAMES

class Cloud:
    def __init__(s, rng): s.rng = rng; s.P = []; s.C = []; s.K = []; s.I = []; s.objs = []
    def add(s, pts, rgb, cls, inten=120):
        n = len(pts)
        if n == 0: return
        col = np.clip(np.array(rgb)[None, :] + s.rng.normal(0, 8, (n, 3)), 0, 255)
        s.P.append(pts); s.C.append(col); s.K.append(np.full(n, cls, np.uint8)); s.I.append(np.full(n, inten, np.uint16))
    def box(s, c, dims, yaw, rgb, cls, dens=900, inten=150):
        """c center xyz, dims (w along face, d depth outward, h), yaw = math angle of outward normal"""
        w, d, h = dims; area = 2 * (w * d + w * h + d * h); n = max(40, int(area * dens))
        r = s.rng.random((n, 3)) - 0.5; face = s.rng.integers(0, 3, n); sgn = np.where(s.rng.random(n) < .5, -.5, .5)
        r[np.arange(n), face] = sgn
        loc = r * np.array([w, d, h])
        ca, sa = math.cos(yaw), math.sin(yaw)
        # local x = tangent (face), local y = outward normal
        nx, ny = ca, sa; tx, ty = -sa, ca
        X = c[0] + loc[:, 0] * tx + loc[:, 1] * nx; Y = c[1] + loc[:, 0] * ty + loc[:, 1] * ny; Z = c[2] + loc[:, 2]
        s.add(np.c_[X, Y, Z], rgb, cls, inten)
    def cyl(s, a, b, r0, r1, rgb, cls, dens=500, inten=110):
        a, b = np.array(a, float), np.array(b, float); L = np.linalg.norm(b - a)
        n = max(30, int(2 * math.pi * max(r0, r1) * L * dens))
        t = s.rng.random(n); th = s.rng.random(n) * 2 * math.pi; r = r0 + (r1 - r0) * t
        ax = (b - a) / L; tmp = np.array([1, 0, 0]) if abs(ax[0]) < .9 else np.array([0, 1, 0])
        e1 = np.cross(ax, tmp); e1 /= np.linalg.norm(e1); e2 = np.cross(ax, e1)
        pts = a + np.outer(t * L, ax) + (r * np.cos(th))[:, None] * e1 + (r * np.sin(th))[:, None] * e2
        s.add(pts, rgb, cls, inten)
    def arrays(s):
        return np.vstack(s.P), np.vstack(s.C), np.concatenate(s.K), np.concatenate(s.I)

def build_cloud(site):
    rng = np.random.default_rng(int(site["site_id"][4:]) + 7)
    c = Cloud(rng)
    H = site["height"] * FT
    roof = site["rooftop"]
    # ground and compound
    g = rng.random((42000, 2)) * 80 - 40
    c.add(np.c_[g, rng.normal(0, .04, len(g))], (96, 118, 72), 2, 60)
    cab_dir = math.radians(200)
    horiz = site["horiz_field"] * FT
    if not roof:
        cp = rng.random((9000, 2)) * 16 - 8
        c.add(np.c_[cp, .05 + rng.normal(0, .02, len(cp))], (150, 148, 140), 2, 90)
        for k in range(4):  # fence
            for t in np.linspace(-9, 9, 120):
                p = [(t, -9), (t, 9), (-9, t), (9, t)][k]
                z = rng.random(12) * 2.4
                c.add(np.c_[np.full(12, p[0]) + rng.normal(0, .02, 12), np.full(12, p[1]) + rng.normal(0, .02, 12), z], (120, 120, 118), 1, 70)
    # structure
    base_z = 0.0
    if roof:
        bw, bd, bh = 36, 26, site["height"] * FT
        c.box((0, 0, bh / 2), (bw, bd, bh), math.pi / 2, (178, 170, 160), 6, dens=30, inten=80)
        top = rng.random((50000, 2)) * [bw, bd] - [bw / 2, bd / 2]
        c.add(np.c_[top, np.full(len(top), bh) + rng.normal(0, .02, len(top))], (160, 158, 152), 6, 80)
        base_z = bh
        c.objs.append(dict(obj="building", cls="Building", center=[0, 0, bh / 2], dims=[bw, bd, bh]))
    elif site["structure"] == "Monopole":
        c.cyl((0, 0, 0), (0, 0, H), .8, .38, (168, 170, 172), 15, dens=260)
    elif site["structure"].startswith("Self"):
        legs = [(math.cos(a), math.sin(a)) for a in (math.pi / 2, math.pi / 2 + 2.094, math.pi / 2 + 4.189)]
        for lx, ly in legs: c.cyl((lx * 5, ly * 5, 0), (lx * 1.2, ly * 1.2, H), .12, .08, (160, 162, 165), 15, dens=900)
        for k in range(14):
            z0, z1 = H * k / 14, H * (k + 1) / 14; f0, f1 = 5 - 3.8 * k / 14, 5 - 3.8 * (k + 1) / 14
            for i in range(3):
                a, b = legs[i], legs[(i + 1) % 3]
                c.cyl((a[0] * f0, a[1] * f0, z0), (b[0] * f1, b[1] * f1, z1), .05, .05, (160, 162, 165), 15, dens=900)
    else:
        legs = [(math.cos(a) * .35, math.sin(a) * .35) for a in (math.pi / 2, math.pi / 2 + 2.094, math.pi / 2 + 4.189)]
        for lx, ly in legs: c.cyl((lx, ly, 0), (lx, ly, H), .05, .05, (160, 60, 50), 15, dens=1400)
        for fr in (.33, .66, .95):
            for a in (math.pi / 2, math.pi / 2 + 2.094, math.pi / 2 + 4.189):
                c.cyl((0, 0, H * fr), (math.cos(a) * H * .6, math.sin(a) * H * .6, 0), .015, .015, (60, 60, 60), 14, dens=2500)
    # cabinet + ice bridge
    if roof:
        cab = (-12, -8, base_z + .9)
    else:
        cab = (math.cos(cab_dir) * (horiz + .9), math.sin(cab_dir) * (horiz + .9), .9)
    c.box(cab, (1.6, .9, 1.8), cab_dir, (205, 205, 200), 68, dens=900)
    c.objs.append(dict(obj=f"{site['site_id']}-CAB1", cls="Equipment cabinet", center=list(cab), dims=[1.6, .9, 1.8]))
    return c, base_z

def build_equipment(site, c, base_z):
    """Equipment AS FOUND in the field (existing and to-be-removed devices only)."""
    rng = c.rng
    field = [d for d in site["devices"] if d["in_field"]]
    R = {"Monopole": 1.9, "Self-support tower": 2.8, "Guyed tower": 1.5}.get(site["structure"], 0)
    tops = []
    for sc in site["sectors"]:
        n = sc["name"]; az = math.radians(sc["az_field"])
        u = np.array([math.sin(az), math.cos(az)]); v = np.array([math.cos(az), -math.sin(az)])
        yaw = math.atan2(u[1], u[0])
        here = [d for d in field if d["sector"] == n]
        if site["rooftop"]:
            if not sc["sled_field"]: continue
            fc = u * 13
            c.box((fc[0], fc[1], base_z + .15), (4.2, 1.4, .3), yaw, (110, 110, 112), 66, dens=700)
            c.objs.append(dict(obj=f"{site['site_id']}-{n}-SLED", cls="Roof sled", sector=SN[n], center=[fc[0], fc[1], base_z + .15], dims=[4.2, 1.4, .3], az=sc["az_field"]))
            mount_z = None
        else:
            if not here: continue
            rc_m = max(d["rc_field"] for d in here) * FT
            fc = u * R
            c.cyl((0, 0, rc_m - .9), (fc[0], fc[1], rc_m - .9), .05, .05, (120, 120, 125), 66, dens=1500)
            c.cyl((fc[0] - v[0] * 1.9, fc[1] - v[1] * 1.9, rc_m - .9), (fc[0] + v[0] * 1.9, fc[1] + v[1] * 1.9, rc_m - .9), .045, .045, (120, 120, 125), 66, dens=1500)
            tops.append(rc_m)
        for p in (1, 2, 3):
            pinfo = site["positions"].get((n, p))
            devs_p = [d for d in here if d["pos"] == p]
            has_pipe = (pinfo and pinfo["pipe_field"]) or bool(devs_p)
            if not has_pipe: continue
            pp = fc + v * (p - 2) * 1.2
            rc = max([d["rc_field"] for d in devs_p], default=site["height"] - 5) * FT
            if site["rooftop"]: rc = base_z + 2.4
            c.cyl((pp[0], pp[1], rc - 1.2), (pp[0], pp[1], rc + 1.2), .037, .037, (125, 125, 130), 66, dens=2500)
            c.objs.append(dict(obj=f"{site['site_id']}-{n}{p}-PIPE", cls="Mount pipe", sector=SN[n], position=p, center=[pp[0], pp[1], rc], dims=[.073, .073, 2.4]))
            ants = [d for d in devs_p if d["kind"] in ("passive", "air")]
            for k, d in enumerate(ants):
                cat = M.CATALOG[d["key"]]; ac = pp + u * (.22 + k * .3)
                zc = (d["rc_field"] * FT) if not site["rooftop"] else rc
                c.box((ac[0], ac[1], zc), (cat["w_m"], cat["d_m"], cat["h_m"]), yaw, (226, 226, 222), 64, dens=1100, inten=200)
                c.objs.append(dict(obj=d["id"], cls="Antenna", sector=SN[n], position=p, model=cat["model"], center=[float(ac[0]), float(ac[1]), zc],
                                   dims=[cat["w_m"], cat["d_m"], cat["h_m"]], az=sc["az_field"], rc_ft=round(zc / FT, 1)))
            for k, d in enumerate([d for d in devs_p if d["kind"] == "radio"]):
                cat = M.CATALOG[d["key"]]; rp = pp - u * .2 + v * (k % 2 - .5) * .45
                zc = (d["rc_field"] * FT if not site["rooftop"] else rc) - 1.25 - (k // 2) * .6
                c.box((rp[0], rp[1], zc), (cat["w_m"], cat["d_m"], cat["h_m"]), yaw, (70, 72, 76), 65, dens=1300, inten=140)
                c.objs.append(dict(obj=d["id"], cls="Remote radio", sector=SN[n], position=p, model=cat["model"], center=[float(rp[0]), float(rp[1]), zc],
                                   dims=[cat["w_m"], cat["d_m"], cat["h_m"]], az=sc["az_field"]))
    # existing cable run
    if not site["rooftop"] and tops:
        top = max(tops)
        cd = math.radians(200); bx, by = math.cos(cd) * .9, math.sin(cd) * .9
        c.cyl((bx, by, .5), (bx, by, top - .5), .06, .06, (25, 25, 25), 67, dens=1500)
        cab = [o for o in c.objs if o["cls"] == "Equipment cabinet"][0]["center"]
        c.cyl((cab[0], cab[1], 2.6), (bx, by, 2.6), .12, .12, (90, 90, 95), 67, dens=900)
        c.objs.append(dict(obj=f"{site['site_id']}-ROUTE", cls="Cable route (cabinet to tower)", center=[(cab[0] + bx) / 2, (cab[1] + by) / 2, 2.6],
                           length_ft=round(math.hypot(cab[0] - bx, cab[1] - by) / FT, 1)))
    elif site["rooftop"]:
        cab = [o for o in c.objs if o["cls"] == "Equipment cabinet"][0]["center"]
        c.objs.append(dict(obj=f"{site['site_id']}-ROUTE", cls="Cable route (cabinet to sleds)", center=cab, length_ft=site["horiz_field"]))

def write_las(site, c, path):
    P, C, K, I = c.arrays()
    lat0 = math.radians(site["lat"])
    hdr = laspy.LasHeader(point_format=7, version="1.4")
    hdr.offsets = [0, 0, 0]; hdr.scales = [0.001, 0.001, 0.001]
    hdr.system_identifier = "SYNTHETIC DRONE LIDAR"; hdr.generating_software = "InnoSquares POC generator"
    las = laspy.LasData(hdr)
    las.x, las.y, las.z = P[:, 0], P[:, 1], P[:, 2]
    las.red, las.green, las.blue = (C[:, 0] * 256).astype(np.uint16), (C[:, 1] * 256).astype(np.uint16), (C[:, 2] * 256).astype(np.uint16)
    las.intensity = I; las.classification = K
    las.gps_time = np.linspace(0, 900, len(P)); las.return_number = np.ones(len(P), np.uint8); las.number_of_returns = np.ones(len(P), np.uint8)
    las.write(path)
    return len(P)

# ---------------------------------------------------------------- rendering
SKY_TOP, SKY_BOT = np.array([150, 190, 230]), np.array([220, 232, 244]); GROUND = np.array([98, 118, 76]); HAZE = np.array([196, 206, 214])
def render(P, C, eye, target, W, H, fov=55, splat=2, boxes=()):
    f = np.array(target, float) - np.array(eye, float); f /= np.linalg.norm(f)
    r = np.cross(f, [0, 0, 1]); r /= np.linalg.norm(r); u = np.cross(r, f)
    Q = P - eye; x, y, z = Q @ r, Q @ u, Q @ f
    m = z > .5; x, y, z, col = x[m], y[m], z[m], C[m]
    fp = (W / 2) / math.tan(math.radians(fov) / 2)
    px = (W / 2 + fp * x / z).astype(int); py = (H / 2 - fp * y / z).astype(int)
    img = np.zeros((H, W, 3)); t = np.linspace(0, 1, H)[:, None]
    img[:] = (SKY_TOP * (1 - t) + SKY_BOT * t)[:, None, :]
    gx, gy = np.meshgrid((np.arange(W) - W / 2) / fp, (np.arange(H) - H / 2) / fp)
    dx_ = f[0] + r[0] * gx - u[0] * gy; dy_ = f[1] + r[1] * gx - u[1] * gy; dz = f[2] + r[2] * gx - u[2] * gy
    with np.errstate(divide="ignore", invalid="ignore"):
        tt = -eye[2] / dz
        hx, hy = eye[0] + tt * dx_, eye[1] + tt * dy_
    near = (dz < 0) & (np.abs(hx) < 40) & (np.abs(hy) < 40)
    img[(dz < 0) & ~near] = HAZE
    img[near] = GROUND
    zbuf = np.full((H, W), np.inf); zbuf[near] = tt[near]
    D = np.stack([dx_, dy_, dz], -1); E = np.array(eye, float)
    for lo, hi, colr in boxes:
        lo, hi = np.array(lo), np.array(hi)
        with np.errstate(divide="ignore", invalid="ignore"):
            t1 = (lo - E) / D; t2 = (hi - E) / D
        tn = np.nanmax(np.minimum(t1, t2), -1); tf = np.nanmin(np.maximum(t1, t2), -1)
        hit = (tf >= tn) & (tf > 0)
        ax_ = np.nanargmax(np.minimum(t1, t2), -1)
        shade = np.choose(ax_, [0.86, 0.93, 1.0])
        hit &= tn < zbuf
        img[hit] = (np.array(colr)[None, :] * shade[hit][:, None]); zbuf[hit] = tn[hit]
    order = np.argsort(-z)  # far to near: near overwrites
    px, py, z, col = px[order], py[order], z[order], col[order]
    sz = np.clip((splat * 18 / z).astype(int), splat, splat + 3)
    for dx in range(-(splat + 2), splat + 3):
        for dy in range(-(splat + 2), splat + 3):
            X, Y = px + dx, py + dy; k = (X >= 0) & (X < W) & (Y >= 0) & (Y < H) & (abs(dx) < sz) & (abs(dy) < sz)
            k[k] &= z[k] < zbuf[Y[k], X[k]] + 0.4
            img[Y[k], X[k]] = col[k]
    return img.clip(0, 255).astype(np.uint8)

def ortho(P, C, half=40, N=900):
    img = np.zeros((N, N, 3), np.uint8); img[:] = GROUND
    gx = ((P[:, 0] + half) / (2 * half) * N).astype(int); gy = ((half - P[:, 1]) / (2 * half) * N).astype(int)
    k = (gx >= 0) & (gx < N) & (gy >= 0) & (gy < N)
    gx, gy, z, col = gx[k], gy[k], P[k, 2], C[k]
    o = np.argsort(z)
    for dx in (0, 1, -1, 2):
        for dy in (0, 1, -1, 2):
            X, Y = np.clip(gx[o] + dx, 0, N - 1), np.clip(gy[o] + dy, 0, N - 1)
            img[Y, X] = col[o].astype(np.uint8)
    return img

def imagery(site, c, folder, vid_path):
    P, C, _, _ = c.arrays()
    H = (site["height"] + (8 if site["rooftop"] else 0)) * FT
    out = []
    Image.fromarray(ortho(P, C)).save(f"{folder}/{site['site_id']}_ortho_stitched.jpg", quality=85)
    out.append(dict(file=f"{site['site_id']}_ortho_stitched.jpg", type="Orthomosaic (stitched, nadir)", gsd_cm=round(80 / 900 * 100, 1)))
    mz = (H - 3) if not site["rooftop"] else site["height"] * FT + 2
    bx = [((-18, -13, 0), (18, 13, site["height"] * FT - .03), (176, 170, 162))] if site["rooftop"] else []
    for sc in site["sectors"]:
        a = math.radians(sc["az"])
        if site["rooftop"]:
            eye = (math.sin(a) * 34, math.cos(a) * 34, mz + 16); tgt = (math.sin(a) * 11, math.cos(a) * 11, mz)
        else:
            eye = (math.sin(a) * 18, math.cos(a) * 18, mz + 3); tgt = (0, 0, mz)
        img = render(P, C, eye, tgt, 1600, 1100, fov=60 if site["rooftop"] else 38, splat=3, boxes=bx)
        fn = f"{site['site_id']}_sector_{SN[sc['name']].lower()}.jpg"; Image.fromarray(img).save(f"{folder}/{fn}", quality=85)
        out.append(dict(file=fn, type=f"Oblique sector view ({SN[sc['name']]})", camera_xyz_m=[round(x, 2) for x in eye], look_at_m=[round(x, 2) for x in tgt], fov_deg=38))
    eye = (55, -55, H * .55); img = render(P, C, eye, (0, 0, H * .5), 1100, 1600, fov=60, splat=2, boxes=bx)
    fn = f"{site['site_id']}_elevation_full.jpg"; Image.fromarray(img).save(f"{folder}/{fn}", quality=85)
    out.append(dict(file=fn, type="Full-structure elevation", camera_xyz_m=[55, -55, round(H * .55, 2)], look_at_m=[0, 0, round(H * .5, 2)], fov_deg=60))
    # orbit video
    frames = 72; wr = iio.get_writer(vid_path, fps=12, codec="libx264", quality=5, macro_block_size=16)
    for i in range(frames):
        t = i / frames; a = 2 * math.pi * t
        if site["rooftop"]:
            eye = (math.cos(a) * 55, math.sin(a) * 55, H + 12 + 10 * t); tgt = (0, 0, H - 3)
        else:
            eye = (math.cos(a) * 32, math.sin(a) * 32, H * (.55 + .4 * t)); tgt = (0, 0, H * (.5 + .45 * t))
        wr.append_data(render(P, C, eye, tgt, 960, 544, fov=58, splat=2, boxes=bx))
    wr.close()
    return out

def vendor_measurements(site, c, rng):
    rows = []
    for o in c.objs:
        if o["cls"] not in ("Antenna", "Remote radio", "Mount pipe", "Roof sled"): continue
        x, y, z = o["center"]
        az = (math.degrees(math.atan2(x, y)) + 360) % 360
        conf = round(float(rng.uniform(.82, .98)), 2)
        guess = o.get("model", "") if (o["cls"] == "Antenna" and rng.random() < .7) else ""
        rows.append(dict(object_id=f"OBJ-{len(rows)+1:03d}", object_type=o["cls"], sector_inferred=o.get("sector", ""),
                         bearing_from_structure_deg=round(az + rng.normal(0, 1.2), 1),
                         facing_azimuth_deg=round(o["az"] + rng.normal(0, 1.5), 1) if "az" in o and o["cls"] == "Antenna" else "",
                         center_height_ft=round(z / FT + rng.normal(0, .3), 1),
                         height_in=round(o["dims"][2] / .0254 + rng.normal(0, .8), 1), width_in=round(o["dims"][0] / .0254 + rng.normal(0, .6), 1),
                         depth_in=round(o["dims"][1] / .0254 + rng.normal(0, .4), 1), model_guess=guess, confidence=conf))
    route = [o for o in c.objs if o["cls"].startswith("Cable route")][0]
    rows.append(dict(object_id=f"OBJ-{len(rows)+1:03d}", object_type=route["cls"], sector_inferred="", bearing_from_structure_deg="",
                     facing_azimuth_deg="", center_height_ft="", height_in="", width_in="", depth_in="", model_guess="",
                     confidence=round(float(rng.uniform(.85, .95)), 2), route_length_ft=round(route["length_ft"] + rng.normal(0, .8), 1)))
    return rows
