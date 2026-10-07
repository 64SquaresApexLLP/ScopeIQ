import os, json, csv, hashlib, shutil, sys, numpy as np
from multiprocessing import Pool
import model as M, docs as Dz, cd as CD, drone as DR

ROOT = "./Ericsson_Scoping_POC_Synthetic_Data"
SN = M.SECT_NAMES

def site_files(i):
    S = M.build_sites(); s = S[i]; sid = s["site_id"]; base = f"{ROOT}/sites/{sid}"
    for d in ("rfds", "cds", "drone/imagery", "drone/video", "ma_sa", "bom"): os.makedirs(f"{base}/{d}", exist_ok=True)
    D = Dz.dates(s); idx = []
    def rec(rel, typ, fmt, rev, date): idx.append([sid, rel, typ, fmt, rev, date.isoformat()])
    # RFDS
    if s["rfds_fmt"] == "xlsx-v2":
        Dz.write_rfds_v2(s, f"{base}/rfds/{sid}_RFDS_R3.xlsx"); rec(f"sites/{sid}/rfds/{sid}_RFDS_R3.xlsx", "RFDS", "XLSX (template v2)", "R3", D["rfds_r3"])
    elif s["rfds_fmt"] == "xlsx-v3":
        Dz.write_rfds_v3(s, f"{base}/rfds/{sid}_RFDS_R3.xlsx"); rec(f"sites/{sid}/rfds/{sid}_RFDS_R3.xlsx", "RFDS", "XLSX (template v3)", "R3", D["rfds_r3"])
    else:
        Dz.write_rfds_pdf(s, f"{base}/rfds/{sid}_RFDS_R3.pdf"); rec(f"sites/{sid}/rfds/{sid}_RFDS_R3.pdf", "RFDS", "PDF", "R3", D["rfds_r3"])
    # CDs
    dxf = f"{base}/cds/{sid}_CD_REV1.dxf" if "dxf" in s["cd_fmt"] else None
    CD.build(s, dxf, f"{base}/cds/{sid}_CD_REV1.pdf")
    rec(f"sites/{sid}/cds/{sid}_CD_REV1.pdf", "Construction Drawings", "PDF (vector, CAD-exported)", "REV 1", D["cd"])
    if dxf: rec(f"sites/{sid}/cds/{sid}_CD_REV1.dxf", "Construction Drawings", "DXF (AutoCAD R2018)", "REV 1", D["cd"])
    # MA/SA
    Dz.write_ma_sa(s, f"{base}/ma_sa/{sid}_MA_SA_R0.pdf"); rec(f"sites/{sid}/ma_sa/{sid}_MA_SA_R0.pdf", "MA/SA", "PDF", "R0", D["ma"])
    # REV0 BOM
    lines, _ = M.rev0_bom(s)
    Dz.write_bom_xlsx(f"{base}/bom/{sid}_BOM_REV0_preliminary.xlsx", [(sid, M.to_rows(s, lines, "REV 0", "Preliminary"))],
                      "SYNTHETIC SAMPLE. REV 0 preliminary BOM from the Ericsson tool; contains seeded errors for the POC.")
    rec(f"sites/{sid}/bom/{sid}_BOM_REV0_preliminary.xlsx", "BOM REV 0", "XLSX", "REV 0", D["rev0"])
    # Drone
    c, bz = DR.build_cloud(s); DR.build_equipment(s, c, bz)
    npts = DR.write_las(s, c, f"{base}/drone/{sid}_pointcloud.laz")
    imgs = DR.imagery(s, c, f"{base}/drone/imagery", f"{base}/drone/video/{sid}_orbit.mp4")
    rec(f"sites/{sid}/drone/{sid}_pointcloud.laz", "Drone Survey - Point Cloud", "LAZ (LAS 1.4, PDRF 7)", "", D["flight"])
    for im in imgs: rec(f"sites/{sid}/drone/imagery/{im['file']}", "Drone Survey - Imagery", "JPG", "", D["flight"])
    rec(f"sites/{sid}/drone/video/{sid}_orbit.mp4", "Drone Survey - Video", "MP4 (H.264)", "", D["flight"])
    meta = dict(site_id=sid, synthetic=True, survey_vendor="SkyLine Aerial Surveys (synthetic)", flight_date=D["flight"].isoformat(),
                aircraft="DJI Matrice 350 RTK (representative)", lidar_sensor="Zenmuse L2 (representative)",
                site_lat=s["lat"], site_lon=s["lon"],
                coordinate_system="Local ENU in metres. Origin = structure centreline at grade (rooftop: building centre at street grade). +X east, +Y north, +Z up. Azimuth = clockwise from +Y.",
                point_cloud=dict(file=f"{sid}_pointcloud.laz", points=int(npts), format="LAS 1.4 point format 7 (XYZ, RGB, intensity, classification, GPS time)",
                                 classification={"1": "Unclassified", "2": "Ground", "6": "Building", "14": "Guy wire", "15": "Tower structure",
                                                 "64": "Antenna / AAU", "65": "Remote radio", "66": "Mount / pipe / sled", "67": "Cable", "68": "Equipment cabinet"}),
                imagery=imgs, video=dict(file=f"{sid}_orbit.mp4", fps=12, seconds=6, resolution="960x544", path="Orbit, rising"),
                vendor_measurements=f"{sid}_vendor_measurements.csv" if s["vendor_meas"] else None,
                note="Survey captures the site AS FOUND before construction. Imagery and video are renders of the point cloud; equipment labels are not legible.")
    json.dump(meta, open(f"{base}/drone/{sid}_capture_metadata.json", "w"), indent=2)
    rec(f"sites/{sid}/drone/{sid}_capture_metadata.json", "Drone Survey - Metadata", "JSON", "", D["flight"])
    if s["vendor_meas"]:
        rows = DR.vendor_measurements(s, c, np.random.default_rng(int(sid[4:])))
        keys = list(rows[-1].keys())
        with open(f"{base}/drone/{sid}_vendor_measurements.csv", "w", newline="") as f:
            w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(rows)
        rec(f"sites/{sid}/drone/{sid}_vendor_measurements.csv", "Drone Survey - Vendor Measurements", "CSV", "", D["flight"])
    objs = [dict(site_id=sid, **{k: (json.dumps([round(float(x), 3) for x in v]) if isinstance(v, (list, tuple)) else v) for k, v in o.items()}) for o in c.objs]
    return idx, objs

def main():
    if os.path.exists(ROOT): shutil.rmtree(ROOT)
    for d in ("reference", "sitetracker", "answer_key"): os.makedirs(f"{ROOT}/{d}", exist_ok=True)
    S = M.build_sites()
    with Pool(5) as p: res = p.map(site_files, range(len(S)))
    idx = [r for a, _ in res for r in a]; objs = [o for _, b in res for o in b]
    Dz.write_catalog(f"{ROOT}/reference/material_catalog.xlsx"); Dz.write_rules(f"{ROOT}/reference/bom_rules.xlsx")
    Dz.write_sitetracker(S, f"{ROOT}/sitetracker", idx)
    # answer key
    allrows, sheets, diffs, truth = [], [], [], []
    for s in S:
        lines, tp = M.generate_bom(s, "truth"); rows = M.to_rows(s, lines, "REV 1", "Approved (FBA)")
        sheets.append((s["site_id"], rows)); allrows += rows
        r0, tp0 = M.rev0_bom(s)
        agg = lambda L: {k: v for k, v in __import__("functools").reduce(lambda d, l: d.update({(l["sector"], l["key"], l["action"]): d.get((l["sector"], l["key"], l["action"]), 0) + l["qty"] + l["spare"]}) or d, L, {}).items()}
        a, b = agg(lines), agg(r0)
        for k in sorted(set(a) | set(b)):
            if a.get(k, 0) != b.get(k, 0):
                c = M.CATALOG[k[1]]
                diffs.append([s["site_id"], SN.get(k[0], "Site"), k[2], c["model"], c["mfr_pn"], c["cust_pn"], b.get(k, 0), a.get(k, 0), a.get(k, 0) - b.get(k, 0)])
        tr0 = M.trunk_plan(s, "cd"); tr1 = M.trunk_plan(s, "truth")
        truth.append(dict(site_id=s["site_id"], name=s["name"], structure=s["structure"], height_ft=s["height"], scope=s["project"],
                          rfds_format=s["rfds_fmt"], cd_format=s["cd_fmt"], vendor_measurements=s["vendor_meas"],
                          sectors=[dict(sector=SN[x["name"]], az_rfds=x["az"], az_cd=x["az_cd"], az_field=x["az_field"], frame=x["frame"],
                                        roof_sled_cd=x["sled_cd"], roof_sled_field=x["sled_field"]) for x in s["sectors"]],
                          mount_positions=[dict(sector=SN[k[0]], position=k[1], pipe_on_cd=v["pipe_cd"], pipe_in_field=v["pipe_field"]) for k, v in s["positions"].items()],
                          devices=[dict(device_id=d["id"], sector=SN[d["sector"]], position=d["pos"], position_on_cd=d["pos_cd"], model=M.CATALOG[d["key"]]["model"],
                                        kind=d["kind"], status=d["status"], rad_center_ft_design=d["rc"], rad_center_ft_field=d["rc_field"] if d["in_field"] else None,
                                        on_rfds=d["in_rfds"], on_cd=d["in_cd"], in_field=d["in_field"]) for d in s["devices"]],
                          basebands=[M.CATALOG[b]["model"] for b in s["basebands"]],
                          cable_route_ft=dict(cd=s["horiz_cd"], field=s["horiz_field"]), trunk_plan_cd=tr0, trunk_plan_final=tr1,
                          mount_analysis=s["ma"], ma_modifications=[dict(sector=SN[a_], item=M.CATALOG[k]["model"], qty=q) for a_, k, q in s["ma_mods"]],
                          structural_analysis=s["sa"]))
    Dz.write_bom_xlsx(f"{ROOT}/answer_key/final_engineer_BOM_REV1.xlsx", [("All_Lines", allrows)] + sheets,
                      "SYNTHETIC ANSWER KEY: engineer-approved REV 1 BOM (RFDS-governed, field-corrected, MA-compliant).")
    def wcsv(name, cols, rows):
        with open(f"{ROOT}/answer_key/{name}", "w", newline="") as f:
            w = csv.writer(f); w.writerow(cols); w.writerows(rows)
    wcsv("final_engineer_BOM_REV1.csv", M.COLS, allrows)
    wcsv("rev0_vs_final_diff.csv", ["Site ID", "Sector", "Action", "Model", "Manufacturer P/N", "Customer P/N", "REV 0 Total Qty", "Final Total Qty", "Change"], diffs)
    iss = [x for s in S for x in s["issues"]]
    wcsv("seeded_discrepancies.csv", list(iss[0].keys()), [list(x.values()) for x in iss])
    json.dump(truth, open(f"{ROOT}/answer_key/site_truth.json", "w"), indent=2, default=str)
    keys = []
    for o in objs:
        for k in o:
            if k not in keys: keys.append(k)
    with open(f"{ROOT}/answer_key/pointcloud_truth_objects.csv", "w", newline="") as f:
        w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(objs)
    json.dump(dict(issues=len(iss), sites=len(S), final_lines=len(allrows), diffs=len(diffs)), open("stats.json", "w"))

if __name__ == "__main__":
    main()
