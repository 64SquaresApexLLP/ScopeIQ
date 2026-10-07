"""Site models, material catalog, BOM rules engine for the synthetic POC data pack."""
import math, copy, hashlib

FT = 0.3048
TRUNK_STEPS = [100, 150, 200, 250, 300, 350]

# ---------------------------------------------------------------- catalog
def _cpn(key):
    return "CA-" + str(int(hashlib.md5(key.encode()).hexdigest(), 16) % 900000 + 100000)

C = {}
def item(key, cat, sub, mfr, model, pn, desc, uom="EA", supply="VFM", approved="Y", cost=0,
         ports=0, power=0, bands="", tech="", dims=(0, 0, 0)):
    C[key] = dict(key=key, category=cat, subcategory=sub, mfr=mfr, model=model, mfr_pn=pn,
                  cust_pn=_cpn(key), desc=desc, uom=uom, supply=supply, approved=approved,
                  unit_cost=cost, ports=ports, power_w=power, bands=bands, tech=tech,
                  h_m=dims[0], w_m=dims[1], d_m=dims[2])

# Active antennas
item("AIR6449", "Major Equipment", "Active Antenna (AAU)", "Ericsson", "AIR 6449 B77D", "KRD 909 101/11",
     "Active antenna unit, n77 3.7 GHz C-band, 64T64R", supply="CFM", cost=38000, power=1100, bands="n77", tech="NR", dims=(0.90, 0.47, 0.22))
item("AIR6419", "Major Equipment", "Active Antenna (AAU)", "Ericsson", "AIR 6419 B41", "KRD 909 102/11",
     "Active antenna unit, n41 2.5 GHz, 64T64R", supply="CFM", cost=30000, power=900, bands="n41", tech="NR", dims=(0.80, 0.44, 0.20))
# Radios
item("R4449", "Major Equipment", "Remote Radio", "Ericsson", "Radio 4449 B5 B12", "KRC 909 201/1",
     "Remote radio unit, 4T4R, 850 MHz B5 + 700 MHz B12", supply="CFM", cost=9000, ports=4, power=450, bands="B5/B12", tech="LTE/NR", dims=(0.50, 0.34, 0.16))
item("R4460", "Major Equipment", "Remote Radio", "Ericsson", "Radio 4460 B2 B66", "KRC 909 202/1",
     "Remote radio unit, 4T4R, 1900 MHz B2 + AWS B66", supply="CFM", cost=10500, ports=4, power=550, bands="B2/B66", tech="LTE/NR", dims=(0.55, 0.34, 0.17))
item("R4480", "Major Equipment", "Remote Radio", "Ericsson", "Radio 4480 B71 B85", "KRC 909 203/1",
     "Remote radio unit, 4T4R, 600 MHz B71 + 700 MHz B85", supply="CFM", cost=9800, ports=4, power=500, bands="B71/B85", tech="LTE/NR", dims=(0.55, 0.34, 0.18))
item("R2217", "Major Equipment", "Remote Radio", "Ericsson", "Radio 2217 B66A", "KRC 909 290/1",
     "Remote radio unit, 2T2R, AWS B66 (legacy)", supply="CFM", ports=2, power=250, bands="B66", tech="LTE", dims=(0.42, 0.28, 0.14))
item("RRUS11", "Major Equipment", "Remote Radio", "Ericsson", "RRUS 11 B12", "KRC 909 291/1",
     "Remote radio unit, 2T2R, 700 MHz B12 (legacy)", supply="CFM", ports=2, power=250, bands="B12", tech="LTE", dims=(0.40, 0.28, 0.13))
# Passive antennas
item("NNH4", "Major Equipment", "Passive Antenna", "CommScope", "NNH4-65B-R6", "NNH4-65B-R6-SYN",
     "Passive panel antenna, 8-port, 6 ft, 698-2690 MHz", supply="CFM", cost=2400, ports=8, bands="LB/MB", tech="LTE/NR", dims=(1.83, 0.50, 0.20))
item("SBNHH", "Major Equipment", "Passive Antenna", "CommScope", "SBNHH-1D65B", "SBNHH-1D65B-SYN",
     "Passive panel antenna, 6-port, 6 ft (legacy)", supply="CFM", ports=6, bands="LB/MB", tech="LTE", dims=(1.83, 0.30, 0.18))
item("APXV", "Major Equipment", "Passive Antenna", "RFS", "APXVSPP18-C-A20", "APXVSPP18-C-A20-SYN",
     "Passive panel antenna, 4-port, 6 ft (legacy)", supply="CFM", ports=4, bands="MB", tech="LTE", dims=(1.83, 0.30, 0.17))
# Baseband / power
item("BB6648", "Major Equipment", "Baseband", "Ericsson", "Baseband 6648", "KDU 909 301/1", "Baseband unit, 19-inch rack", supply="CFM", cost=14000, tech="LTE/NR")
item("BB6651", "Major Equipment", "Baseband", "Ericsson", "Baseband 6651", "KDU 909 302/1", "Baseband unit, 19-inch rack, high capacity", supply="CFM", cost=16500, tech="LTE/NR")
item("RECT3K", "Power & Grounding", "Rectifier", "Ericsson", "PSU 3000 48V", "BML 909 401/1", "Rectifier module, -48 VDC, 3 kW", supply="CFM", cost=1200)
item("BRK30", "Power & Grounding", "DC Breaker", "Eaton", "DCB-30A", "EAT-DCB-30-SYN", "DC breaker, 30 A, plug-in", cost=45)
item("BRK60", "Power & Grounding", "DC Breaker", "Eaton", "DCB-60A", "EAT-DCB-60-SYN", "DC breaker, 60 A, plug-in", cost=60)
item("OVPT", "Fiber & DC", "Surge Protection", "Raycap", "RC-OVP-6-TOP", "RC-OVP-6T-SYN", "DC surge protection / distribution box, 6-circuit, tower-top", supply="CFM", cost=3200)
item("OVPB", "Fiber & DC", "Surge Protection", "Raycap", "RC-OVP-6-BASE", "RC-OVP-6B-SYN", "DC surge protection box, 6-circuit, base", supply="CFM", cost=2100)
# Cables
for L in TRUNK_STEPS:
    item(f"HYB{L}", "Fiber & DC", "Hybrid Trunk", "CommScope", f"HYB-6x12-{L}", f"HYB-6X12-{L}-SYN",
         f"Hybrid trunk cable, 6 DC pairs + 12 fiber pairs, {L} ft, factory terminated", supply="CFM", cost=12 * L)
for L in (15, 20):
    item(f"DCJ{L}", "Fiber & DC", "DC Jumper", "CommScope", f"DCJ-8AWG-{L}", f"DCJ-8-{L}-SYN", f"DC jumper cable, 2-conductor 8 AWG, {L} ft", cost=4 * L)
    item(f"FJ{L}", "Fiber & DC", "Fiber Jumper", "Corning", f"FJ-LCLC-OD-{L}", f"FJ-LC-OD-{L}-SYN", f"Outdoor fiber jumper, duplex LC-LC single-mode, {L} ft", cost=3 * L)
item("FJ15NA", "Fiber & DC", "Fiber Jumper", "AnyFiber", "AF-LC-15", "AF-LC-15", "Fiber jumper LC-LC 15 ft (NOT customer-approved)", approved="N", cost=20)
item("RFJ6", "RF Connectivity", "RF Jumper", "CommScope", "RFJ-43-6", "RFJ-43-6-SYN", "RF jumper, 1/2 in, 4.3-10 M-M, 6 ft", cost=38)
item("RFJ10", "RF Connectivity", "RF Jumper", "CommScope", "RFJ-43-10", "RFJ-43-10-SYN", "RF jumper, 1/2 in, 4.3-10 M-M, 10 ft", cost=46)
item("SFP10", "Fiber & DC", "Optical Module", "Ericsson", "SFP+ 10G LR", "RDH 909 501/1", "SFP+ optical module, 10 Gb/s, 1310 nm", supply="CFM", cost=140)
item("SFP25", "Fiber & DC", "Optical Module", "Ericsson", "SFP28 25G LR", "RDH 909 502/1", "SFP28 optical module, 25 Gb/s, 1310 nm", supply="CFM", cost=260)
# Mounting
item("PIPE", "Mounting Hardware", "Mount Pipe", "Site Pro 1", "PK-278-8", "SP1-PK278-8-SYN", "Antenna mount pipe kit, 2-7/8 in x 8 ft, with clamps", uom="KIT", cost=310)
item("AIRBRKT", "Mounting Hardware", "AAU Bracket", "Ericsson", "AIR mount bracket kit", "SXK 909 601/1", "AAU tilt bracket kit for 2-3.5 in pipe", uom="KIT", cost=420)
item("RRUMNT", "Mounting Hardware", "RRU Mount", "Site Pro 1", "RRU-MK-2", "SP1-RRUMK2-SYN", "RRU mount kit, dual pipe clamp", uom="KIT", cost=95)
item("FRAME", "Mounting Hardware", "Sector Frame", "Site Pro 1", "SF-12-3P", "SP1-SF12-3P-SYN", "Sector frame, 12 ft face, 3-pipe, with standoff arms", uom="KIT", cost=2600)
item("MRK", "Mounting Hardware", "Mount Reinforcement", "Site Pro 1", "MRK-12", "SP1-MRK12-SYN", "Mount reinforcement kit, 12 ft sector frame", uom="KIT", cost=780)
item("SLED", "Mounting Hardware", "Roof Sled", "Site Pro 1", "NPS-3P", "SP1-NPS3P-SYN", "Non-penetrating roof sled mount, 3-pipe, with ballast trays", uom="KIT", cost=1450)
# Grounding
item("GK6", "Power & Grounding", "Ground Kit", "Harger", "GK-6-TW", "HGR-GK6TW-SYN", "Ground kit, #6 AWG, two-hole lug, 10 ft", uom="KIT", cost=28)
item("GK6NA", "Power & Grounding", "Ground Kit", "Generic", "GND-6", "GND-6", "Ground kit #6 (NOT customer-approved)", uom="KIT", approved="N", cost=12)
item("GKT", "Power & Grounding", "Trunk Ground Kit", "Harger", "GK-TRK-12", "HGR-GKTRK-SYN", "Trunk ground kit for hybrid cable up to 1.25 in", uom="KIT", cost=36)
item("GBAR", "Power & Grounding", "Ground Bar", "Harger", "GB-20-TT", "HGR-GB20-SYN", "Tower-top ground bar, 20-hole, tinned copper", cost=85)
# Ancillary
item("HANGER", "Ancillary", "Cable Support", "CommScope", "SNAP-3S", "SNAP-3S-SYN", "Snap-in hanger, 3-stack", cost=6)
item("HOIST", "Ancillary", "Cable Support", "CommScope", "HG-125", "HG-125-SYN", "Hoist grip for hybrid cable", cost=40)
item("WPK", "Ancillary", "Weatherproofing", "CommScope", "WPK-UNIV", "WPK-UNIV-SYN", "Weatherproofing kit (butyl mastic + vinyl tape)", uom="KIT", cost=22)
item("LABEL", "Ancillary", "Labeling", "Brady", "LBL-SET-RF", "BRD-LBLRF-SYN", "Cable and equipment label set", uom="SET", cost=18)
item("TIES", "Ancillary", "Consumables", "Thomas & Betts", "CT-UV-100", "TB-CTUV100-SYN", "Cable ties, UV-resistant, 100-pack", uom="BAG", cost=14)
item("HWKIT", "Ancillary", "Consumables", "Site Pro 1", "HW-SS-KIT", "SP1-HWSS-SYN", "Stainless hardware kit (bolts, nuts, washers)", uom="KIT", cost=55)
item("HEAT", "Ancillary", "Consumables", "TE Connectivity", "HS-KIT", "TE-HSKIT-SYN", "Heat-shrink kit, assorted", uom="KIT", cost=30)

CATALOG = C
KIND = {k: ("air" if v["subcategory"].startswith("Active") else "radio" if v["subcategory"] == "Remote Radio"
            else "passive" if v["subcategory"] == "Passive Antenna" else "other") for k, v in C.items()}

# ---------------------------------------------------------------- rules (documentation + engine share these IDs)
RULES = [
    ("R-RAD-01", "New remote radio", "RRUMNT", "1 per radio", ""),
    ("R-RAD-02", "New remote radio", "DCJ15", "1 per radio", "OVP to radio"),
    ("R-RAD-03", "New remote radio", "FJ15", "1 per radio", "OVP to radio"),
    ("R-RAD-04", "New remote radio", "SFP10", "2 per radio", "1 at radio, 1 at baseband"),
    ("R-RAD-05", "New remote radio", "GK6", "1 per radio", ""),
    ("R-RAD-06", "New remote radio feeding a passive antenna", "RFJ6", "ports per radio", "4.3-10 jumpers radio to antenna"),
    ("R-RAD-07", "New remote radio", "WPK", "1 per radio", ""),
    ("R-RAD-08", "New remote radio", "LABEL", "1 per radio", ""),
    ("R-RAD-09", "New remote radio", "BRK30", "1 per radio", "Breaker at base power plant"),
    ("R-AIR-01", "New AAU", "AIRBRKT", "1 per AAU", ""),
    ("R-AIR-02", "New AAU", "DCJ20", "1 per AAU", "OVP to AAU"),
    ("R-AIR-03", "New AAU", "FJ20", "1 per AAU", "OVP to AAU"),
    ("R-AIR-04", "New AAU", "SFP25", "2 per AAU", "1 at AAU, 1 at baseband"),
    ("R-AIR-05", "New AAU", "GK6", "1 per AAU", ""),
    ("R-AIR-06", "New AAU", "WPK", "1 per AAU", ""),
    ("R-AIR-07", "New AAU", "LABEL", "1 per AAU", ""),
    ("R-AIR-08", "New AAU", "BRK60", "1 per AAU", "Breaker at base power plant"),
    ("R-ANT-01", "New passive antenna", "GK6", "1 per antenna", ""),
    ("R-ANT-02", "New passive antenna", "LABEL", "1 per antenna", ""),
    ("R-MNT-01", "New antenna or AAU at a position with no mount pipe", "PIPE", "1 per position", "Not needed when a new sector frame or roof sled supplies pipes"),
    ("R-MNT-02", "Sector marked for new frame", "FRAME", "1 per sector", ""),
    ("R-MNT-03", "Rooftop sector with new equipment and no roof sled", "SLED", "1 per sector", "Sled supplies 3 pipes"),
    ("R-MNT-04", "Mount analysis requires reinforcement", "MRK", "per MA", "Quantity and sectors from MA report"),
    ("R-GND-01", "Sector with any new device", "GBAR", "1 per sector", ""),
    ("R-TRK-01", "New powered devices (radios + AAUs)", "HYB*", "ceil(devices / 6) trunks", "Length = next catalog step >= 1.10 x (vertical + horizontal run)"),
    ("R-TRK-02", "Per hybrid trunk", "OVPT", "1 per trunk", ""),
    ("R-TRK-03", "Per hybrid trunk", "OVPB", "1 per trunk", ""),
    ("R-TRK-04", "Per hybrid trunk", "HANGER", "ceil(trunk length ft / 3) per trunk", "Hanger every 3 ft"),
    ("R-TRK-05", "Per hybrid trunk", "HOIST", "1 per trunk", ""),
    ("R-TRK-06", "Per hybrid trunk", "GKT", "3 per trunk if length > 200 ft, else 2", "Top, bottom (and mid-span)"),
    ("R-TRK-07", "Per hybrid trunk", "WPK", "2 per trunk", ""),
    ("R-OVP-01", "Per OVP box", "GK6", "1 per OVP", ""),
    ("R-BB-01", "New baseband", "GK6", "1 per baseband", ""),
    ("R-PWR-01", "Net new DC load", "RECT3K", "ceil(max(0, added W - removed W) / 3000)", ""),
    ("R-SITE-01", "Per site", "TIES", "2 per site (+1 spare)", ""),
    ("R-SITE-02", "Per site", "HWKIT", "1 per site", ""),
    ("R-SITE-03", "Per site", "HEAT", "1 per site", ""),
    ("R-SITE-04", "Per site", "LABEL", "1 per site (+1 spare)", "Trunk and OVP labels"),
    ("R-SITE-05", "Per site", "WPK", "+1 spare per site", ""),
    ("R-EQ-01", "New major equipment (RFDS)", "(device)", "1 per device", "Install line"),
    ("R-RMV-01", "Equipment to remove (RFDS or field)", "(device)", "1 per device", "Removal line, no material"),
]

# ---------------------------------------------------------------- sites
SECT_NAMES = {"A": "Alpha", "B": "Beta", "C": "Gamma", "D": "Delta"}

def _dev(site, sector, pos, key, status, rc, **kw):
    d = dict(id=f"{site['site_id']}-{sector}{pos}-{key}-{len(site['devices'])+1:02d}", sector=sector, pos=pos, key=key,
             kind=KIND[key], status=status, rc=rc, rc_field=rc, in_rfds=True, in_cd=True,
             in_field=status in ("Existing", "Remove"), pos_cd=pos)
    d.update(kw)
    site["devices"].append(d)
    return d

def _pos(site, sector, pos, pipe_cd=True, pipe_field=True):
    site["positions"][(sector, pos)] = dict(pipe_cd=pipe_cd, pipe_field=pipe_field)

def new_site(**kw):
    s = dict(devices=[], positions={}, sectors=[], basebands=[], ma_mods=[], issues=[], rev0_errors=[],
             riser_ft=None, rooftop=False, ma=dict(result="PASS", capacity=78), sa=dict(result="PASS", capacity=81))
    s.update(kw)
    return s

def add_sector(s, name, az, az_cd=None, az_field=None, frame="existing", sled_cd=None, sled_field=None):
    s["sectors"].append(dict(name=name, az=az, az_cd=az if az_cd is None else az_cd, az_field=az if az_field is None else az_field,
                             frame=frame, sled_cd=sled_cd, sled_field=sled_field))

def t1(s, H, rc_air, sectors):
    for n in sectors:
        _pos(s, n, 1); _pos(s, n, 2); _pos(s, n, 3)
        _dev(s, n, 1, "NNH4", "Existing", H - 5); _dev(s, n, 1, "R4449", "Existing", H - 5); _dev(s, n, 1, "R4460", "Existing", H - 5)
        _dev(s, n, 2, "APXV", "Existing", H - 5); _dev(s, n, 2, "R2217", "Existing", H - 5)
        _dev(s, n, 3, "AIR6449", "New", rc_air)
    s["basebands"].append("BB6648")

def t2(s, H, rc_air, sectors, pipe3=False):
    for n in sectors:
        _pos(s, n, 1); _pos(s, n, 2); _pos(s, n, 3, pipe_cd=pipe3, pipe_field=pipe3)
        _dev(s, n, 1, "NNH4", "Existing", H - 5); _dev(s, n, 1, "R4449", "Existing", H - 5); _dev(s, n, 1, "R4460", "Existing", H - 5)
        _dev(s, n, 2, "APXV", "Remove", H - 5); _dev(s, n, 2, "R2217", "Remove", H - 5)
        _dev(s, n, 2, "NNH4", "New", H - 5); _dev(s, n, 2, "R4480", "New", H - 5)
        _dev(s, n, 3, "AIR6419", "New", rc_air)
    s["basebands"].append("BB6651")

def t3(s, H, sectors):
    for n in sectors:
        _pos(s, n, 1); _pos(s, n, 2); _pos(s, n, 3, pipe_cd=False, pipe_field=False)
        _dev(s, n, 1, "SBNHH", "Remove", H - 5); _dev(s, n, 1, "RRUS11", "Remove", H - 5)
        _dev(s, n, 2, "APXV", "Remove", H - 5); _dev(s, n, 2, "R2217", "Remove", H - 5)
        _dev(s, n, 1, "NNH4", "New", H - 5); _dev(s, n, 1, "R4449", "New", H - 5); _dev(s, n, 1, "R4460", "New", H - 5)
        _dev(s, n, 2, "AIR6449", "New", H - 5)
        _dev(s, n, 3, "AIR6419", "New", H - 5)
    s["basebands"] += ["BB6648", "BB6651"]

def find(s, sector, key, status=None):
    for d in s["devices"]:
        if d["sector"] == sector and d["key"] == key and (status is None or d["status"] == status):
            return d
    raise KeyError((sector, key))

def issue(s, iid, cat, docs, desc, action, bom_impact):
    s["issues"].append(dict(issue_id=iid, site_id=s["site_id"], category=cat, revealed_by=docs, description=desc,
                            expected_action=action, bom_impact=bom_impact))

def build_sites():
    S = []
    # 01 -------------------------------------------------------------
    s = new_site(site_id="TXDA1024", name="Lakewood Heights", city="Dallas", zip="75214", addr="6120 Abrams Rd (synthetic)",
                 lat=32.8341, lon=-96.7512, structure="Monopole", height=150, owner="Lonestar Tower Partners",
                 scope="T1", project="5G C-band add", horiz_cd=28, horiz_field=28, rfds_fmt="xlsx-v2", cd_fmt="dxf+pdf",
                 vendor_meas=True, flight="2026-08-11", cx_sp="Prairie Tower Services")
    for n, az in zip("ABC", (0, 120, 240)): add_sector(s, n, az)
    t1(s, 150, 138, "ABC")
    s["positions"][("B", 3)]["pipe_field"] = False
    issue(s, "TXDA1024-01", "CD vs field", "Drone point cloud, imagery", "CD A-3 shows an existing spare pipe at Beta position 3; drone survey shows no pipe.",
          "Redline CD A-3; add mount pipe kit", "+1 PIPE (Beta)")
    s["rev0_errors"].append(("drop_qty", dict(sector="C", key="GK6", rule="R-AIR-05", n=1)))
    issue(s, "TXDA1024-02", "REV 0 BOM error", "Rules check", "REV 0 omits the ground kit for the new Gamma AAU.",
          "Add ground kit", "+1 GK6 (Gamma)")
    S.append(s)
    # 02 -------------------------------------------------------------
    s = new_site(site_id="TXFW2217", name="Fossil Creek", city="Fort Worth", zip="76137", addr="3900 Basswood Blvd (synthetic)",
                 lat=32.8733, lon=-97.3065, structure="Self-support tower", height=180, owner="Trinity Structures",
                 scope="T1", project="5G C-band add", horiz_cd=30, horiz_field=30, rfds_fmt="xlsx-v2", cd_fmt="dxf+pdf",
                 vendor_meas=True, flight="2026-08-12", cx_sp="Brazos Wireless Construction")
    add_sector(s, "A", 30, az_cd=20, az_field=20); add_sector(s, "B", 130); add_sector(s, "C", 250)
    t1(s, 180, 168, "ABC")
    issue(s, "TXFW2217-01", "RFDS vs CD", "RFDS, CD A-3/A-4", "RFDS sets Alpha azimuth to 30 deg; CDs (and field) show 20 deg.",
          "Raise RFI to confirm re-orientation; redline CD", "None")
    s["rev0_errors"].append(("duplicate", dict(sector="A", key="SFP25")))
    issue(s, "TXFW2217-02", "REV 0 BOM error", "Rules check", "REV 0 lists the Alpha SFP28 25G line twice.",
          "Remove duplicate line", "-2 SFP25 (Alpha duplicate)")
    S.append(s)
    # 03 -------------------------------------------------------------
    s = new_site(site_id="TXPL0588", name="Legacy Drive", city="Plano", zip="75024", addr="5800 Tennyson Pkwy (synthetic)",
                 lat=33.0768, lon=-96.8210, structure="Monopole", height=125, owner="Lonestar Tower Partners",
                 scope="T2", project="n41 add + low-band refresh", horiz_cd=22, horiz_field=22, rfds_fmt="xlsx-v2", cd_fmt="dxf+pdf",
                 vendor_meas=True, flight="2026-08-13", cx_sp="Prairie Tower Services")
    for n, az in zip("ABC", (10, 130, 250)): add_sector(s, n, az)
    t2(s, 125, 113, "ABC")
    _dev(s, "C", 1, "RRUS11", "Remove", 120, in_rfds=False, in_cd=False, in_field=True)
    s["ma"] = dict(result="PASS WITH MODIFICATIONS", capacity=104, capacity_after=92)
    s["ma_mods"] = [("A", "MRK", 1), ("B", "MRK", 1), ("C", "MRK", 1)]
    issue(s, "TXPL0588-01", "CD vs field", "Drone point cloud, vendor measurements", "Unrecorded legacy RRUS 11 B12 on Gamma position 1 pipe; not on RFDS or CDs.",
          "Raise RFI; add removal line; redline CD existing inventory", "+1 Remove RRUS 11 (Gamma)")
    s["rev0_errors"].append(("scale_qty", dict(key="RFJ6", factor=0.5)))
    issue(s, "TXPL0588-02", "REV 0 BOM error", "Rules check", "REV 0 carries 2 RF jumpers per Radio 4480 instead of 4 (4 ports).",
          "Correct quantity", "+2 RFJ6 per sector (+6)")
    issue(s, "TXPL0588-03", "MA requirement", "MA report", "Mount analysis passes only with reinforcement kits on all three sectors; REV 0 omits them.",
          "Add mount reinforcement kits", "+3 MRK")
    S.append(s)
    # 04 -------------------------------------------------------------
    s = new_site(site_id="TXIR1340", name="Valley Ranch", city="Irving", zip="75063", addr="9100 N MacArthur Blvd (synthetic)",
                 lat=32.9234, lon=-96.9587, structure="Monopole", height=140, owner="BluePeak Towers",
                 scope="T1", project="5G C-band add", horiz_cd=35, horiz_field=35, rfds_fmt="xlsx-v2", cd_fmt="pdf",
                 vendor_meas=True, flight="2026-08-14", cx_sp="Brazos Wireless Construction")
    for n, az in zip("ABC", (0, 120, 240)): add_sector(s, n, az)
    t1(s, 140, 128, "ABC")
    for d in s["devices"]:
        if d["status"] == "Existing": d["rc_field"] = d["rc"] - 4
    issue(s, "TXIR1340-01", "CD vs field", "Drone point cloud, vendor measurements", "Existing antennas measured at 131 ft rad center; CDs and RFDS show 135 ft.",
          "Raise RFI; redline CD elevation", "None (trunk length step unchanged)")
    s["rev0_errors"].append(("swap_pn", dict(key="FJ20", to="FJ15NA")))
    issue(s, "TXIR1340-02", "REV 0 BOM error", "Catalog check", "REV 0 uses a non-approved fiber jumper (AF-LC-15) for the AAUs.",
          "Replace with approved FJ-LCLC-OD-20", "Swap 3 x AF-LC-15 for 3 x FJ20")
    S.append(s)
    # 05 -------------------------------------------------------------
    s = new_site(site_id="TXGR0719", name="Arbor Bend", city="Grand Prairie", zip="75052", addr="2400 S Great Southwest Pkwy (synthetic)",
                 lat=32.7092, lon=-97.0143, structure="Self-support tower", height=195, owner="Trinity Structures",
                 scope="T3", project="Full site modernization", horiz_cd=40, horiz_field=80, rfds_fmt="xlsx-v3", cd_fmt="dxf+pdf",
                 vendor_meas=True, flight="2026-08-15", cx_sp="Redline Constructors")
    for n, az in zip("ABC", (60, 180, 300)): add_sector(s, n, az, frame="new")
    t3(s, 195, "ABC")
    find(s, "B", "R4460", "New")["in_cd"] = False
    s["sa"] = dict(result="FAIL", capacity=103)
    issue(s, "TXGR0719-01", "RFDS vs CD", "RFDS, CD A-3/A-4", "RFDS adds Radio 4460 B2 B66 at Beta position 1; CDs omit it.",
          "Raise RFI; BOM follows RFDS; redline CD", "+1 R4460 (Beta) and its dependent package")
    issue(s, "TXGR0719-02", "CD vs field", "Drone point cloud, imagery", "Measured cabinet-to-tower route is 80 ft; CD cable schedule uses 40 ft.",
          "Redline CD A-4; step trunk length", "2 x HYB300 -> 2 x HYB350; hangers +34")
    issue(s, "TXGR0719-03", "SA requirement", "SA report", "Structural analysis at 103% of capacity (FAIL).",
          "Escalate; structural modification outside BOM scope", "None (flag)")
    S.append(s)
    # 06 -------------------------------------------------------------
    s = new_site(site_id="TXDE0831", name="Hickory Flats", city="Denton", zip="76210", addr="4500 Teasley Ln (synthetic)",
                 lat=33.1580, lon=-97.0877, structure="Guyed tower", height=220, owner="BluePeak Towers",
                 scope="T2", project="n41 add + low-band refresh", horiz_cd=26, horiz_field=26, rfds_fmt="xlsx-v3", cd_fmt="dxf+pdf",
                 vendor_meas=False, flight="2026-08-18", cx_sp="Redline Constructors")
    add_sector(s, "A", 0, az_field=348); add_sector(s, "B", 120); add_sector(s, "C", 240)
    t2(s, 220, 208, "ABC")
    issue(s, "TXDE0831-01", "CD vs field", "Drone point cloud, imagery", "Alpha antennas measured at 348 deg; RFDS and CDs specify 0 deg (12 deg off).",
          "Raise RFI; add re-orientation to SoW", "None")
    s["rev0_errors"].append(("set_qty", dict(key="HANGER", qty=84)))
    issue(s, "TXDE0831-02", "REV 0 BOM error", "Rules check", "REV 0 sizes hangers for a 250 ft trunk; the specified trunk is 300 ft.",
          "Correct quantity", "+16 HANGER")
    S.append(s)
    # 07 -------------------------------------------------------------
    s = new_site(site_id="TXRI0906", name="Collins Tower", city="Richardson", zip="75080", addr="1300 E Collins Blvd (synthetic)",
                 lat=32.9857, lon=-96.7108, structure="Rooftop", height=85, owner="Collins Tower LLC (building owner)",
                 scope="T1", project="5G C-band add + new sector", horiz_cd=60, horiz_field=60, riser_ft=10, rooftop=True,
                 rfds_fmt="xlsx-v3", cd_fmt="dxf+pdf", vendor_meas=False, flight="2026-08-19", cx_sp="Prairie Tower Services")
    for n, az in zip("ABC", (30, 120, 210)): add_sector(s, n, az, sled_cd=True, sled_field=True)
    add_sector(s, "D", 300, sled_cd=True, sled_field=False)
    t1(s, 96, 93, "ABC")
    _pos(s, "D", 3, pipe_cd=True, pipe_field=False)
    _dev(s, "D", 3, "AIR6449", "New", 93)
    issue(s, "TXRI0906-01", "CD vs field", "Drone point cloud, imagery", "CDs show an existing roof sled for new Delta sector; roof has none.",
          "Redline CD; add roof sled", "+1 SLED (Delta)")
    s["rev0_errors"].append(("drop_key", dict(key="BRK60")))
    issue(s, "TXRI0906-02", "REV 0 BOM error", "Rules check", "REV 0 omits the 60 A DC breakers for all four AAUs.",
          "Add breakers", "+4 BRK60")
    S.append(s)
    # 08 -------------------------------------------------------------
    s = new_site(site_id="TXMK1112", name="Lake Forest", city="McKinney", zip="75071", addr="3300 Lake Forest Dr (synthetic)",
                 lat=33.2178, lon=-96.6743, structure="Monopole", height=165, owner="Lonestar Tower Partners",
                 scope="T3", project="Full site modernization", horiz_cd=30, horiz_field=30, rfds_fmt="pdf", cd_fmt="dxf+pdf",
                 vendor_meas=False, flight="2026-08-20", cx_sp="Brazos Wireless Construction")
    for n, az in zip("ABC", (20, 140, 260)): add_sector(s, n, az, frame="new")
    t3(s, 165, "ABC")
    s["positions"][("C", 3)]["pipe_field"] = True
    _dev(s, "C", 3, "APXV", "Remove", 160, in_rfds=False, in_cd=False, in_field=True)
    issue(s, "TXMK1112-01", "CD vs field", "Drone point cloud, imagery", "Unrecorded legacy APXV antenna on a third Gamma pipe; not on RFDS or CDs.",
          "Raise RFI; add removal line", "+1 Remove APXV (Gamma)")
    s["rev0_errors"].append(("trunks", dict(n=1)))
    issue(s, "TXMK1112-02", "REV 0 BOM error", "Rules check", "REV 0 carries one hybrid trunk for 12 new powered devices (needs 2).",
          "Add second trunk and its package", "+1 HYB250, +1 OVPT, +1 OVPB, +84 HANGER, +1 HOIST, +3 GKT, +2 WPK, +2 GK6")
    S.append(s)
    # 09 -------------------------------------------------------------
    s = new_site(site_id="TXAD0405", name="Uptown Plaza", city="Addison", zip="75001", addr="15600 Dallas Pkwy (synthetic)",
                 lat=32.9587, lon=-96.8295, structure="Rooftop", height=60, owner="Uptown Plaza Holdings (building owner)",
                 scope="T2", project="n41 add + low-band refresh", horiz_cd=45, horiz_field=45, riser_ft=10, rooftop=True,
                 rfds_fmt="pdf", cd_fmt="pdf", vendor_meas=False, flight="2026-08-21", cx_sp="Redline Constructors")
    for n, az in zip("AB", (90, 270)): add_sector(s, n, az, sled_cd=True, sled_field=True)
    t2(s, 68, 68, "AB", pipe3=True)
    find(s, "B", "AIR6419")["pos_cd"] = 2
    find(s, "B", "NNH4", "New")["pos_cd"] = 3
    find(s, "B", "R4480")["pos_cd"] = 3
    issue(s, "TXAD0405-01", "RFDS vs CD", "RFDS, CD A-3", "RFDS places the Beta AIR 6419 at position 3; CDs show it at position 2 (swapped with the new NNH4).",
          "Raise RFI; redline CD", "None")
    s["rev0_errors"].append(("drop_key", dict(key="WPK")))
    issue(s, "TXAD0405-02", "REV 0 BOM error", "Rules check", "REV 0 omits all weatherproofing kits.",
          "Add weatherproofing kits", "+7 WPK (4 sector, 2 trunk, 1 spare)")
    S.append(s)
    # 10 -------------------------------------------------------------
    s = new_site(site_id="TXCA0977", name="Carrollton Station", city="Carrollton", zip="75006", addr="1900 E Belt Line Rd (synthetic)",
                 lat=32.9537, lon=-96.8903, structure="Monopole", height=110, owner="BluePeak Towers",
                 scope="T1", project="5G C-band add", horiz_cd=45, horiz_field=18, rfds_fmt="pdf", cd_fmt="dxf+pdf",
                 vendor_meas=False, flight="2026-08-22", cx_sp="Prairie Tower Services")
    for n, az in zip("ABC", (45, 165, 285)): add_sector(s, n, az)
    t1(s, 110, 98, "ABC")
    s["ma"] = dict(result="PASS WITH MODIFICATIONS", capacity=101, capacity_after=88)
    s["ma_mods"] = [("A", "MRK", 1)]
    issue(s, "TXCA0977-01", "CD vs field", "Drone point cloud, imagery", "Measured cabinet-to-tower route is 18 ft; CD cable schedule uses 45 ft.",
          "Redline CD A-4; step trunk down", "HYB200 -> HYB150; hangers -17")
    issue(s, "TXCA0977-02", "MA requirement", "MA report", "Mount analysis requires a reinforcement kit on Alpha; REV 0 omits it.",
          "Add mount reinforcement kit", "+1 MRK (Alpha)")
    S.append(s)
    for s in S:
        s["market"] = "DFW"; s["state"] = "TX"; s["customer"] = "CARRIER-A"
        s["rfds_rev"] = "R3"; s["cd_rev"] = "REV 1"
    return S

# ---------------------------------------------------------------- engine
def devices(s, mode):
    if mode == "truth":
        return [d for d in s["devices"] if d["in_rfds"] or (d["in_field"] and not d["in_cd"])]
    return [d for d in s["devices"] if d["in_cd"]]

def trunk_plan(s, mode, n_override=None):
    devs = [d for d in devices(s, mode) if d["status"] == "New" and d["kind"] in ("radio", "air")]
    n = math.ceil(len(devs) / 6) if devs else 0
    if n_override: n = n_override
    horiz = s["horiz_field"] if mode == "truth" else s["horiz_cd"]
    vert = s["riser_ft"] if s["rooftop"] else max(d["rc"] for d in devs) + 5
    req = (vert + horiz) * 1.10
    L = next(x for x in TRUNK_STEPS if x >= req)
    return dict(count=n, vertical=vert, horizontal=horiz, required=round(req, 1), length=L, devices=len(devs))

def generate_bom(s, mode):
    devs = devices(s, mode)
    lines = []
    src_rfds = f"RFDS {s['rfds_rev']}"
    field = mode == "truth"
    def add(sector, key, qty, rule, action="Install", parent=None, source="", spare=0):
        if qty <= 0 and spare <= 0: return
        p = CATALOG[parent] if parent else CATALOG[key]
        lines.append(dict(sector=sector, key=key, qty=qty, spare=spare, rule=rule, action=action,
                          tech=p["tech"] or "", band=p["bands"] or "", parent=parent or "", source=source))
    # major equipment + removals
    for d in devs:
        sec = d["sector"]
        if d["status"] == "New":
            add(sec, d["key"], 1, "R-EQ-01", source=f"{src_rfds}; CD A-3")
        elif d["status"] == "Remove":
            src = "Drone survey" if (d["in_field"] and not d["in_cd"]) else f"{src_rfds}; CD A-3"
            add(sec, d["key"], 1, "R-RMV-01", action="Remove", source=src)
    for bb in s["basebands"]:
        add("SITE", bb, 1, "R-EQ-01", source=f"{src_rfds} Baseband & Power")
        add("SITE", "GK6", 1, "R-BB-01", parent=bb, source="CD E-1")
    # device packages
    for d in devs:
        if d["status"] != "New": continue
        sec, k = d["sector"], d["key"]
        if d["kind"] == "radio":
            ports = CATALOG[k]["ports"]
            for key, q, r, src in [("RRUMNT", 1, "R-RAD-01", "CD A-3"), ("DCJ15", 1, "R-RAD-02", "CD A-4"), ("FJ15", 1, "R-RAD-03", "CD A-4"),
                                   ("SFP10", 2, "R-RAD-04", "CD A-4"), ("GK6", 1, "R-RAD-05", "CD E-1"), ("RFJ6", ports, "R-RAD-06", "CD A-4"),
                                   ("WPK", 1, "R-RAD-07", "Customer standard"), ("LABEL", 1, "R-RAD-08", "Customer standard"), ("BRK30", 1, "R-RAD-09", "CD E-1")]:
                add(sec, key, q, r, parent=k, source=src)
        elif d["kind"] == "air":
            for key, q, r, src in [("AIRBRKT", 1, "R-AIR-01", "CD A-3"), ("DCJ20", 1, "R-AIR-02", "CD A-4"), ("FJ20", 1, "R-AIR-03", "CD A-4"),
                                   ("SFP25", 2, "R-AIR-04", "CD A-4"), ("GK6", 1, "R-AIR-05", "CD E-1"), ("WPK", 1, "R-AIR-06", "Customer standard"),
                                   ("LABEL", 1, "R-AIR-07", "Customer standard"), ("BRK60", 1, "R-AIR-08", "CD E-1")]:
                add(sec, key, q, r, parent=k, source=src)
        elif d["kind"] == "passive":
            add(sec, "GK6", 1, "R-ANT-01", parent=k, source="CD E-1")
            add(sec, "LABEL", 1, "R-ANT-02", parent=k, source="Customer standard")
    # mounting
    for sc in s["sectors"]:
        n = sc["name"]
        new_here = [d for d in devs if d["sector"] == n and d["status"] == "New"]
        if not new_here: continue
        add(n, "GBAR", 1, "R-GND-01", source="CD E-1")
        if sc["frame"] == "new":
            add(n, "FRAME", 1, "R-MNT-02", source="CD A-3")
            continue
        if s["rooftop"]:
            sled = sc["sled_field"] if field else sc["sled_cd"]
            if not sled:
                add(n, "SLED", 1, "R-MNT-03", source="Drone survey; CD A-3" if field else "CD A-3")
                continue
        mounted = {d["pos"] if field else d["pos_cd"] for d in new_here if d["kind"] in ("air", "passive")}
        for p in sorted(mounted):
            pinfo = s["positions"].get((n, p), dict(pipe_cd=False, pipe_field=False))
            has = pinfo["pipe_field"] if field else pinfo["pipe_cd"]
            if not has:
                src = "Drone survey; CD A-3" if field and pinfo["pipe_cd"] else "CD A-3"
                add(n, "PIPE", 1, "R-MNT-01", source=src)
    if field:
        for sec, key, q in s["ma_mods"]:
            add(sec, key, q, "R-MNT-04", source="MA report")
    # trunks
    tp = trunk_plan(s, mode)
    if tp["count"]:
        tsrc = "CD A-4; Drone survey (measured route)" if field and s["horiz_field"] != s["horiz_cd"] else "CD A-4"
        n, L = tp["count"], tp["length"]
        add("SITE", f"HYB{L}", n, "R-TRK-01", source=tsrc)
        add("SITE", "OVPT", n, "R-TRK-02", source="CD A-4")
        add("SITE", "OVPB", n, "R-TRK-03", source="CD A-4")
        add("SITE", "HANGER", n * math.ceil(L / 3), "R-TRK-04", source=tsrc)
        add("SITE", "HOIST", n, "R-TRK-05", source="CD A-4")
        add("SITE", "GKT", n * (3 if L > 200 else 2), "R-TRK-06", source="CD E-1")
        add("SITE", "WPK", 2 * n, "R-TRK-07", source="Customer standard")
        add("SITE", "GK6", 2 * n, "R-OVP-01", source="CD E-1")
    # power
    added = sum(CATALOG[d["key"]]["power_w"] for d in devs if d["status"] == "New")
    removed = sum(CATALOG[d["key"]]["power_w"] for d in devs if d["status"] == "Remove")
    add("SITE", "RECT3K", math.ceil(max(0, added - removed) / 3000), "R-PWR-01", source=f"{src_rfds} Baseband & Power")
    # site consumables
    add("SITE", "TIES", 2, "R-SITE-01", spare=1, source="Customer standard")
    add("SITE", "HWKIT", 1, "R-SITE-02", source="Customer standard")
    add("SITE", "HEAT", 1, "R-SITE-03", source="Customer standard")
    add("SITE", "LABEL", 1, "R-SITE-04", spare=1, source="Customer standard")
    add("SITE", "WPK", 0, "R-SITE-05", spare=1, source="Customer standard")
    return lines, tp

def apply_rev0_errors(s, lines):
    lines = copy.deepcopy(lines)
    for kind, a in s["rev0_errors"]:
        if kind == "drop_qty":
            for l in lines:
                if l["sector"] == a["sector"] and l["key"] == a["key"] and l["rule"] == a["rule"]:
                    l["qty"] -= a["n"]; break
        elif kind == "duplicate":
            l = next(l for l in lines if l["sector"] == a["sector"] and l["key"] == a["key"])
            lines.insert(lines.index(l) + 1, dict(l))
        elif kind == "scale_qty":
            for l in lines:
                if l["key"] == a["key"]: l["qty"] = int(l["qty"] * a["factor"])
        elif kind == "swap_pn":
            for l in lines:
                if l["key"] == a["key"]: l["key"] = a["to"]
        elif kind == "set_qty":
            for l in lines:
                if l["key"] == a["key"]: l["qty"] = a["qty"]
        elif kind == "drop_key":
            lines = [l for l in lines if l["key"] != a["key"]]
    return [l for l in lines if l["qty"] > 0 or l["spare"] > 0]

def rev0_bom(s):
    lines, tp = generate_bom(s, "cd")
    for kind, a in s["rev0_errors"]:
        if kind == "trunks":  # rebuild trunk-dependent lines with the wrong trunk count
            n, L = a["n"], tp["length"]
            fix = {"R-TRK-01": n, "R-TRK-02": n, "R-TRK-03": n, "R-TRK-04": n * math.ceil(L / 3), "R-TRK-05": n,
                   "R-TRK-06": n * (3 if L > 200 else 2), "R-TRK-07": 2 * n, "R-OVP-01": 2 * n}
            for l in lines:
                if l["rule"] in fix: l["qty"] = fix[l["rule"]]
    return apply_rev0_errors(s, lines), tp

COLS = ["Site ID", "Market", "Sector", "Technology", "Band", "Equipment Category", "Manufacturer", "Model", "Manufacturer P/N",
        "Customer P/N", "Description", "UOM", "Design Qty", "Spare Qty", "Total Qty", "Supply (CFM/VFM)", "Action",
        "Source Drawing", "BOM Rule", "Revision", "Status"]

def to_rows(s, lines, rev, status):
    rows = []
    for l in lines:
        c = CATALOG[l["key"]]
        sec = SECT_NAMES.get(l["sector"], "Site")
        rows.append([s["site_id"], s["market"], sec, l["tech"], l["band"], c["category"], c["mfr"], c["model"], c["mfr_pn"],
                     c["cust_pn"], c["desc"], c["uom"], l["qty"], l["spare"], l["qty"] + l["spare"],
                     "N/A (existing)" if l["action"] == "Remove" else c["supply"], l["action"], l["source"], l["rule"], rev, status])
    return rows
