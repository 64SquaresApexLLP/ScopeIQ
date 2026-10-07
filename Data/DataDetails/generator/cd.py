"""Construction drawings: AutoCAD DXF (block attributes, layers, schedules) and a PDF sheet set rendered from it."""
import math
import ezdxf
from ezdxf.enums import TextEntityAlignment as TA
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import model as M
import docs as Dz

SN = M.SECT_NAMES
W, H, GAP = 340, 220, 400
SHEETS = [("T-1", "TITLE SHEET & SCOPE OF WORK"), ("A-2", "ELEVATION"), ("A-3", "ANTENNA LAYOUT PLAN"),
          ("A-4", "ANTENNA & CABLE SCHEDULE"), ("E-1", "GROUNDING PLAN & NOTES")]

def _blocks(doc):
    def attdefs(b, tags, vis=("MODEL",)):
        for i, t in enumerate(tags):
            b.add_attdef(t, (0, -3 - 1.6 * i), dxfattribs={"height": 1.2, "flags": 0 if t in vis else 1})
    b = doc.blocks.new("ANT_PANEL"); b.add_lwpolyline([(-4, 0), (4, 0), (4, 2.5), (-4, 2.5)], close=True)
    attdefs(b, ["SECTOR", "POSITION", "MFR", "MODEL", "STATUS", "AZIMUTH", "RAD_CENTER_FT", "MECH_TILT"], vis=())
    b = doc.blocks.new("AAU"); b.add_lwpolyline([(-3, 0), (3, 0), (3, 2.8), (-3, 2.8)], close=True); b.add_line((-3, 0), (3, 2.8)); b.add_line((-3, 2.8), (3, 0))
    attdefs(b, ["SECTOR", "POSITION", "MFR", "MODEL", "STATUS", "AZIMUTH", "RAD_CENTER_FT", "MECH_TILT"], vis=())
    b = doc.blocks.new("RRU"); b.add_lwpolyline([(-1.6, 0), (1.6, 0), (1.6, 1.4), (-1.6, 1.4)], close=True)
    attdefs(b, ["SECTOR", "POSITION", "MODEL", "STATUS", "BANDS"], vis=())
    b = doc.blocks.new("PIPE"); b.add_circle((0, 0), 0.9)
    attdefs(b, ["SECTOR", "POSITION", "STATUS"], vis=())
    b = doc.blocks.new("SLED"); b.add_lwpolyline([(-16, -3), (16, -3), (16, 3), (-16, 3)], close=True)
    attdefs(b, ["SECTOR", "STATUS"], vis=())
    b = doc.blocks.new("OVP"); b.add_lwpolyline([(-1.5, -1), (1.5, -1), (1.5, 1), (-1.5, 1)], close=True); b.add_line((-1.5, -1), (1.5, 1))
    attdefs(b, ["LOCATION", "MODEL", "STATUS"], vis=())

LAYERS = [("A-BORDER", 7), ("A-TITLE", 7), ("A-STRUCT", 7), ("A-ANT-EXIST", 8), ("A-ANT-NEW", 1), ("A-ANT-REMOVE", 30),
          ("A-RRU-EXIST", 8), ("A-RRU-NEW", 1), ("A-RRU-REMOVE", 30), ("A-MOUNT", 5), ("A-CABLE", 3), ("A-TEXT", 7),
          ("A-TABLE", 7), ("A-DIM", 4), ("E-GROUND", 2)]

def lay(status, kind):
    base = "RRU" if kind == "radio" else "ANT"
    return f"A-{base}-" + {"Existing": "EXIST", "New": "NEW", "Remove": "REMOVE"}[status]

def tag(status):
    return {"Existing": "(E)", "New": "(P)", "Remove": "(R)"}[status]

def build(s, dxf_path=None, pdf_path=None):
    doc = ezdxf.new("R2018", setup=True); doc.header["$INSUNITS"] = 0
    for n, c in LAYERS: doc.layers.add(n, color=c)
    doc.layers.get("A-ANT-REMOVE").dxf.linetype = "DASHED"; doc.layers.get("A-RRU-REMOVE").dxf.linetype = "DASHED"
    _blocks(doc)
    msp = doc.modelspace()
    devs = [d for d in s["devices"] if d["in_cd"]]
    tp = M.trunk_plan(s, "cd")
    D = Dz.dates(s)

    def text(x, y, t, hgt=2.0, layer="A-TEXT", align=None):
        e = msp.add_text(t, height=hgt, dxfattribs={"layer": layer, "style": "OpenSans"})
        if align: e.set_placement((x, y), align=align)
        else: e.set_placement((x, y))
        return e

    def rect(x0, y0, x1, y1, layer):
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})

    def sheet_frame(i):
        ox = i * GAP; num, title = SHEETS[i]
        rect(ox, 0, ox + W, H, "A-BORDER"); rect(ox + 4, 4, ox + W - 4, H - 4, "A-BORDER")
        rect(ox + W - 58, 4, ox + W - 4, H - 4, "A-TITLE")
        rows = ["MERIDIAN A&E GROUP", "(SYNTHETIC SAMPLE)", "", "CLIENT: ERICSSON", f"CARRIER: {s['customer']}", "",
                f"SITE ID: {s['site_id']}", f"SITE: {s['name'].upper()}", s["addr"].upper()[:26], f"{s['city'].upper()}, TX {s['zip']}", "",
                f"STRUCTURE: {s['structure'].upper()}", f"HEIGHT: {s['height']} FT", "", f"REV {s['cd_rev'].split()[-1]}  {D['cd'].isoformat()}",
                "ISSUED FOR CONSTRUCTION", "", "NOT FOR CONSTRUCTION -", "SYNTHETIC POC DATA"]
        for j, r in enumerate(rows): text(ox + W - 55, H - 12 - j * 5.2, r, 1.7, "A-TITLE")
        text(ox + W - 55, 30, "SHEET TITLE:", 1.6, "A-TITLE"); text(ox + W - 55, 24, title, 1.8, "A-TITLE")
        text(ox + W - 55, 12, f"SHEET {num}", 3.2, "A-TITLE")
        return ox

    # ---------------- T-1
    ox = sheet_frame(0)
    text(ox + 12, 200, f"{s['customer']} - {s['project'].upper()}", 5); text(ox + 12, 192, f"{s['site_id']}  {s['name'].upper()}", 3.5)
    text(ox + 12, 180, "SCOPE OF WORK", 3)
    sow = []
    from collections import Counter
    for st, verb in (("New", "INSTALL"), ("Remove", "REMOVE")):
        cnt = Counter(M.CATALOG[d["key"]]["model"] for d in devs if d["status"] == st)
        for m, q in cnt.items(): sow.append(f"{verb} ({q}) {m.upper()}")
    for bb in s["basebands"]: sow.append(f"INSTALL (1) {M.CATALOG[bb]['model'].upper()} IN EXISTING CABINET")
    if tp["count"]: sow.append(f"INSTALL ({tp['count']}) HYBRID TRUNK 6x12, {tp['length']} FT, WITH TOP AND BASE OVP")
    if any(sc["frame"] == "new" for sc in s["sectors"]): sow.append("REPLACE EXISTING T-ARMS WITH NEW 12 FT SECTOR FRAMES")
    sow.append("FIELD VERIFY ALL EXISTING CONDITIONS PRIOR TO CONSTRUCTION")
    for j, l in enumerate(sow): text(ox + 14, 172 - j * 5, f"{j+1}. {l}", 2.2)
    y0 = 172 - len(sow) * 5 - 8
    text(ox + 12, y0, "SHEET INDEX", 3)
    for j, (n, t) in enumerate(SHEETS): text(ox + 14, y0 - 8 - j * 5, f"{n}   {t}", 2.2)
    text(ox + 150, 180, "SITE INFORMATION", 3)
    for j, (k, v) in enumerate(Dz.site_info(s)[:14]): text(ox + 152, 172 - j * 5, f"{k.upper()}: {v}", 2.0)
    text(ox + 150, 95, "GENERAL NOTES", 3)
    notes = ["CONTRACTOR SHALL VERIFY ALL DIMENSIONS AND EXISTING", "CONDITIONS BEFORE ORDERING MATERIAL.",
             "ALL WORK PER CARRIER BUILD STANDARDS AND TIA-222-H.", "RF CONFIGURATION PER RFDS " + s["rfds_rev"] + ".",
             "MOUNT AND STRUCTURAL ADEQUACY PER MA/SA REPORTS."]
    for j, l in enumerate(notes): text(ox + 152, 87 - j * 5, l, 2.0)

    # ---------------- A-2 elevation
    ox = sheet_frame(1)
    Htop = s["height"] + (15 if s["rooftop"] else 0)
    sc_ = 150 / Htop; gx, gy = ox + 120, 30
    Y = lambda ft: gy + ft * sc_
    msp.add_line((ox + 12, gy), (ox + 270, gy), dxfattribs={"layer": "A-STRUCT"}); text(ox + 14, gy - 5, "FINISHED GRADE 0'-0\"", 2)
    if s["rooftop"]:
        rect(gx - 70, gy, gx + 70, Y(s["height"]), "A-STRUCT"); text(gx - 68, Y(s["height"]) + 2, f"TOP OF ROOF {s['height']}'-0\"", 2, "A-DIM")
    elif s["structure"] == "Monopole":
        msp.add_lwpolyline([(gx - 3.5, gy), (gx + 3.5, gy), (gx + 1.8, Y(s["height"])), (gx - 1.8, Y(s["height"]))], close=True, dxfattribs={"layer": "A-STRUCT"})
    elif s["structure"].startswith("Self"):
        for sgn in (-1, 1): msp.add_line((gx + sgn * 16, gy), (gx + sgn * 3, Y(s["height"])), dxfattribs={"layer": "A-STRUCT"})
        for k in range(1, 12):
            f0, f1 = (k - 1) / 11, k / 11
            w0, w1 = 16 - 13 * f0, 16 - 13 * f1
            msp.add_line((gx - w0, gy + f0 * (Y(s["height"]) - gy)), (gx + w1, gy + f1 * (Y(s["height"]) - gy)), dxfattribs={"layer": "A-STRUCT"})
            msp.add_line((gx + w0, gy + f0 * (Y(s["height"]) - gy)), (gx - w1, gy + f1 * (Y(s["height"]) - gy)), dxfattribs={"layer": "A-STRUCT"})
    else:
        for sgn in (-1, 1): msp.add_line((gx + sgn * 2, gy), (gx + sgn * 2, Y(s["height"])), dxfattribs={"layer": "A-STRUCT"})
        for fr in (0.33, 0.66, 0.95):
            for sgn in (-1, 1): msp.add_line((gx, gy + fr * (Y(s["height"]) - gy)), (gx + sgn * 95, gy), dxfattribs={"layer": "A-STRUCT"})
        text(gx + 60, gy + 4, "GUY WIRES (E)", 1.8)
    if not s["rooftop"]: text(gx + 6, Y(s["height"]) + 2, f"TOP OF STRUCTURE {s['height']}'-0\"", 2, "A-DIM")
    nsec = len(s["sectors"]); labels = []
    for i, sc in enumerate(s["sectors"]):
        cx = gx + (i - (nsec - 1) / 2) * 26
        for d in [d for d in devs if d["sector"] == sc["name"] and d["kind"] in ("passive", "air")]:
            x = cx + (d["pos_cd"] - 2) * 7; hh = M.CATALOG[d["key"]]["h_m"] / M.FT * sc_
            rect(x - 1.5, Y(d["rc"]) - hh / 2, x + 1.5, Y(d["rc"]) + hh / 2, lay(d["status"], d["kind"]))
            t = f"{sc['name']}{d['pos_cd']}" + ("R" if d["status"] == "Remove" else "")
            text(x - 1.5, Y(d["rc"]) + hh / 2 + 1, t, 1.3); labels.append((t, d))
        rads = [d for d in devs if d["sector"] == sc["name"] and d["kind"] == "radio"]
        for j, d in enumerate(rads):
            x = cx + (d["pos_cd"] - 2) * 7 + 2.5; y = Y(d["rc"]) - 6 - (j % 2) * 3
            rect(x, y, x + 2, y + 2.5, lay(d["status"], d["kind"]))
    if tp["count"] and not s["rooftop"]:
        topy = Y(tp["vertical"])
        msp.add_line((gx + 4, gy + 2), (gx + 4, topy), dxfattribs={"layer": "A-CABLE"})
        msp.add_line((gx + 4, gy + 2), (gx + 60, gy + 2), dxfattribs={"layer": "A-CABLE"})
        rect(gx + 60, gy, gx + 72, gy + 12, "A-STRUCT"); text(gx + 60, gy + 13, "(E) EQUIPMENT CABINET", 1.6)
        text(gx + 20, gy + 4, f"(P) HYBRID TRUNK - HORIZ RUN {tp['horizontal']} FT", 1.5, "A-CABLE")
    rcs = sorted({d["rc"] for d in devs})
    for rc in rcs:
        msp.add_line((ox + 12, Y(rc)), (gx - 50, Y(rc)), dxfattribs={"layer": "A-DIM"}); text(ox + 14, Y(rc) + 1, f"RAD CENTER {rc}'-0\"", 1.8, "A-DIM")
    text(ox + 200, 205, "EQUIPMENT KEY", 2.4)
    for j, (t, d) in enumerate(labels[:28]):
        text(ox + 200, 199 - j * 5.6, f"{t:<4} {tag(d['status'])} {M.CATALOG[d['key']]['model']} RC {d['rc']}'", 1.6)

    # ---------------- A-3 plan
    ox = sheet_frame(2)
    cx, cy = ox + 130, 110
    if s["rooftop"]:
        rect(cx - 112, cy - 92, cx + 112, cy + 92, "A-STRUCT"); text(cx - 93, cy - 68, "ROOF OUTLINE (E)", 1.8)
    elif s["structure"] == "Monopole":
        msp.add_circle((cx, cy), 4, dxfattribs={"layer": "A-STRUCT"})
    else:
        msp.add_lwpolyline([(cx, cy + 6), (cx - 5.2, cy - 3), (cx + 5.2, cy - 3)], close=True, dxfattribs={"layer": "A-STRUCT"})
    msp.add_line((ox + 20, 185), (ox + 20, 200), dxfattribs={"layer": "A-TEXT"}); text(ox + 18, 202, "N", 3)
    for sc in s["sectors"]:
        az = math.radians(sc["az_cd"]); u = (math.sin(az), math.cos(az)); v = (math.cos(az), -math.sin(az))
        R = 68 if s["rooftop"] else 52
        fc = (cx + u[0] * R, cy + u[1] * R)
        msp.add_line((cx + u[0] * 6, cy + u[1] * 6), fc, dxfattribs={"layer": "A-MOUNT"})
        msp.add_line((fc[0] - v[0] * 22, fc[1] - v[1] * 22), (fc[0] + v[0] * 22, fc[1] + v[1] * 22), dxfattribs={"layer": "A-MOUNT"})
        lx, ly = cx + u[0] * (R + 30), cy + u[1] * (R + 30)
        text(lx, ly, f"{SN[sc['name']].upper()} {sc['az_cd']} DEG", 2.2, align=TA.MIDDLE_CENTER)
        if s["rooftop"]:
            r = msp.add_blockref("SLED", fc, dxfattribs={"rotation": -sc["az_cd"], "layer": "A-MOUNT"})
            r.add_auto_attribs({"SECTOR": SN[sc["name"]], "STATUS": "EXISTING" if sc["sled_cd"] else "PROPOSED"})
            text(fc[0] - u[0] * 8, fc[1] - u[1] * 8, "(E) ROOF SLED" if sc["sled_cd"] else "(P) ROOF SLED", 1.5, align=TA.MIDDLE_CENTER)
        for p in (1, 2, 3):
            pp = (fc[0] + v[0] * (p - 2) * 15, fc[1] + v[1] * (p - 2) * 15)
            pi = s["positions"].get((sc["name"], p))
            if sc["frame"] == "new": st = "PROPOSED (NEW FRAME)"
            elif pi and pi["pipe_cd"]:
                st = "EXISTING" if any(d["sector"] == sc["name"] and d["pos_cd"] == p and d["status"] != "New" for d in devs) else "EXISTING SPARE"
            else: st = None
            if st:
                r = msp.add_blockref("PIPE", pp, dxfattribs={"layer": "A-MOUNT"})
                r.add_auto_attribs({"SECTOR": SN[sc["name"]], "POSITION": str(p), "STATUS": st})
            here = [d for d in devs if d["sector"] == sc["name"] and d["pos_cd"] == p]
            for k, d in enumerate([d for d in here if d["kind"] in ("passive", "air")]):
                off = 3.5 + k * 5.5
                ip = (pp[0] + u[0] * off, pp[1] + u[1] * off)
                c = M.CATALOG[d["key"]]; mt, _, _ = Dz.tilts(s, d)
                r = msp.add_blockref("AAU" if d["kind"] == "air" else "ANT_PANEL", ip, dxfattribs={"rotation": -sc["az_cd"], "layer": lay(d["status"], d["kind"]), "xscale": 0.8, "yscale": 0.8})
                r.add_auto_attribs({"SECTOR": SN[sc["name"]], "POSITION": str(p), "MFR": c["mfr"], "MODEL": c["model"],
                                    "STATUS": d["status"].upper(), "AZIMUTH": str(sc["az_cd"]), "RAD_CENTER_FT": str(d["rc"]), "MECH_TILT": str(mt)})
                tp_ = (pp[0] + u[0] * (off + 1.2) + v[0] * 6.5, pp[1] + u[1] * (off + 1.2) + v[1] * 6.5)
                text(tp_[0], tp_[1], f"{sc['name']}{p} {tag(d['status'])} {c['model']}", 1.25, align=TA.MIDDLE_LEFT)
            for k, d in enumerate([d for d in here if d["kind"] == "radio"]):
                ip = (pp[0] - u[0] * (3 + k * 2.2), pp[1] - u[1] * (3 + k * 2.2))
                c = M.CATALOG[d["key"]]
                r = msp.add_blockref("RRU", ip, dxfattribs={"rotation": -sc["az_cd"], "layer": lay(d["status"], d["kind"]), "xscale": 0.6, "yscale": 0.6})
                r.add_auto_attribs({"SECTOR": SN[sc["name"]], "POSITION": str(p), "MODEL": c["model"], "STATUS": d["status"].upper(), "BANDS": c["bands"]})
    text(ox + 12, 12, "(E) EXISTING   (P) PROPOSED   (R) REMOVE.  EQUIPMENT DATA HELD IN BLOCK ATTRIBUTES.", 1.8)

    # ---------------- A-4 schedules
    ox = sheet_frame(3)
    def table(x, y, cols, rows, title, rh=4.2, th=1.55):
        text(x, y + 3, title, 2.6)
        tw = sum(w for _, w in cols)
        allr = [[c for c, _ in cols]] + rows
        for i, r in enumerate(allr):
            yy = y - i * rh
            msp.add_line((x, yy), (x + tw, yy), dxfattribs={"layer": "A-TABLE"})
            xx = x
            for (c, w), val in zip(cols, r):
                text(xx + 0.8, yy - rh + 1.2, str(val), th, "A-TABLE"); xx += w
        yb = y - len(allr) * rh
        msp.add_line((x, yb), (x + tw, yb), dxfattribs={"layer": "A-TABLE"})
        xx = x
        for c, w in cols + [("", 0)]:
            msp.add_line((xx, y), (xx, yb), dxfattribs={"layer": "A-TABLE"}); xx += w
        return yb
    cols = [("SECTOR", 18), ("AZ", 10), ("POS", 9), ("STATUS", 18), ("TYPE", 16), ("MANUFACTURER", 26), ("MODEL", 40), ("RC (FT)", 14), ("M-TILT", 13), ("BANDS", 22)]
    rows = []
    for sc in s["sectors"]:
        for d in sorted([d for d in devs if d["sector"] == sc["name"]], key=lambda d: (d["pos_cd"], d["kind"] == "radio")):
            c = M.CATALOG[d["key"]]; mt, _, _ = Dz.tilts(s, d)
            rows.append([SN[sc["name"]].upper(), sc["az_cd"], d["pos_cd"], {"Existing": "EXISTING", "New": "PROPOSED", "Remove": "REMOVE"}[d["status"]],
                         {"air": "AAU", "radio": "RRU", "passive": "ANTENNA"}[d["kind"]], c["mfr"].upper(), c["model"].upper(), d["rc"],
                         mt if d["kind"] != "radio" else "-", c["bands"]])
    rh = 4.2 if len(rows) <= 34 else 3.3
    yb = table(ox + 10, 205, cols, rows, "ANTENNA & EQUIPMENT SCHEDULE", rh=rh, th=1.5 if rh > 4 else 1.25)
    ccols = [("TRUNK", 16), ("TYPE", 34), ("FROM", 30), ("TO", 30), ("VERT (FT)", 17), ("HORIZ (FT)", 18), ("REQ'D (FT)", 18), ("SPECIFIED", 22)]
    crow = [[f"T{i+1}", "HYBRID 6x12", "BASE OVP / CABINET", "TOP OVP", tp["vertical"], tp["horizontal"], tp["required"], f"{tp['length']} FT"] for i in range(tp["count"])]
    yb = table(ox + 10, yb - 10, ccols, crow, "CABLE SCHEDULE (REQ'D = 1.10 x (VERT + HORIZ))")
    nr = sum(1 for d in devs if d["status"] == "New" and d["kind"] == "radio"); na = sum(1 for d in devs if d["status"] == "New" and d["kind"] == "air")
    jrows = [["DC JUMPER 8 AWG", "TOP OVP TO RRU", "15 FT", nr], ["FIBER JUMPER LC-LC", "TOP OVP TO RRU", "15 FT", nr],
             ["DC JUMPER 8 AWG", "TOP OVP TO AAU", "20 FT", na], ["FIBER JUMPER LC-LC", "TOP OVP TO AAU", "20 FT", na]]
    table(ox + 10, yb - 10, [("JUMPER", 40), ("ROUTE", 40), ("LENGTH", 18), ("QTY", 12)], jrows, "JUMPER SCHEDULE")

    # ---------------- E-1 grounding
    ox = sheet_frame(4)
    text(ox + 12, 200, "GROUNDING PLAN", 3)
    msp.add_circle((ox + 120, 115), 55, dxfattribs={"layer": "E-GROUND"}); text(ox + 70, 55, "(E) GROUND RING #2 AWG BARE TINNED", 1.8)
    rect(ox + 115, 110, ox + 125, 116, "E-GROUND"); text(ox + 112, 105, "(E) MGB", 1.8)
    for i, sc in enumerate(s["sectors"]):
        a = math.radians(sc["az_cd"]); px, py = ox + 120 + math.sin(a) * 35, 115 + math.cos(a) * 35
        rect(px - 4, py - 2, px + 4, py + 2, "E-GROUND"); text(px - 6, py + 4, f"(P) {SN[sc['name']].upper()} TOWER-TOP GROUND BAR", 1.4)
        msp.add_line((px, py), (ox + 120, 116), dxfattribs={"layer": "E-GROUND"})
    notes = ["1. BOND EACH NEW RRU, AAU AND ANTENNA TO SECTOR GROUND BAR WITH #6 AWG.", "2. GROUND HYBRID TRUNK AT TOP, BOTTOM AND MID-SPAN IF > 200 FT.",
             "3. BOND TOP AND BASE OVP ENCLOSURES WITH #6 AWG.", "4. ALL LUGS TWO-HOLE, TINNED, WITH ANTI-OXIDANT."]
    for j, n in enumerate(notes): text(ox + 190, 190 - j * 6, n, 1.6)

    if dxf_path: doc.saveas(dxf_path)
    if pdf_path:
        cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK)
        def xof(e):
            t = e.dxftype()
            if t == "LINE": return e.dxf.start.x
            if t in ("TEXT", "INSERT"): return e.dxf.insert.x
            if t == "CIRCLE": return e.dxf.center.x
            if t == "LWPOLYLINE": return e.get_points()[0][0]
            return 0
        groups = {}
        for e in msp: groups.setdefault(int(xof(e) // GAP), []).append(e)
        with PdfPages(pdf_path, metadata={"Title": f"{s['site_id']} Construction Drawings {s['cd_rev']}"}) as pdf:
            for i in range(len(SHEETS)):
                fig = plt.figure(figsize=(17, 11)); ax = fig.add_axes([0, 0, 1, 1])
                fe = Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg)
                fe.draw_entities(groups.get(i, []))
                ax.set_xlim(i * GAP - 3, i * GAP + W + 3); ax.set_ylim(-3, H + 3); ax.set_aspect("equal", adjustable="box"); ax.axis("off")
                pdf.savefig(fig); plt.close(fig)
    return doc
