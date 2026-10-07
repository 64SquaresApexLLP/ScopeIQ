# Ericsson BNEW MACS scoping POC — synthetic input data (10 sites)

Synthetic sample of every input the automated scoping platform consumes, for 10 DFW sites, plus an answer key to score the POC against.
Everything here is invented. Model names are representative; part numbers, customer P/Ns, specs, costs, addresses, people and companies are not real.
**Not for construction or procurement.**

## What is in the pack

| Folder | Input | Format | RFP activity it feeds |
|---|---|---|---|
| `sites/<ID>/rfds/` | RF Data Sheet R3 (existing + final config) | XLSX template v2 (4 sites), XLSX template v3 (3), PDF (3) | Download documentation, SoW summary, Create BOM |
| `sites/<ID>/cds/` | Construction drawings REV 1, sheets T-1, A-2, A-3, A-4, E-1 | PDF for all 10; AutoCAD DXF for 8 (TXIR1340 and TXAD0405 are PDF-only) | Documentation review, redlining, Create BOM |
| `sites/<ID>/drone/` | LiDAR point cloud, stitched ortho + oblique imagery, orbit video, capture metadata | LAZ (LAS 1.4), JPG, MP4, JSON | Field validation, redlining |
| `sites/<ID>/drone/*_vendor_measurements.csv` | Drone vendor's equipment inventory and measurements | CSV (5 sites only) | Field validation |
| `sites/<ID>/ma_sa/` | Mount and structural analysis summaries | PDF | Requirements identification |
| `sites/<ID>/bom/` | Preliminary REV 0 BOM from the Ericsson tool | XLSX | Validate REV 0, create REV 1 |
| `sitetracker/` | Site, Project, Milestone, Document records | CSV (Salesforce-style `__c` fields) | Tool-of-record update |
| `reference/` | Material catalog (CFM/VFM, approved flag) and BOM dependency rules | XLSX | Rules engine |
| `answer_key/` | Engineer-approved REV 1 BOMs, seeded discrepancies, REV 0 vs final diff, site truth model, point-cloud object truth | XLSX, CSV, JSON | POC scoring |
| `generator/` | Python that produced this pack; change `model.py` to add sites | PY | Scaling test data |

`manifest.csv` lists every file with size and SHA-256. `snowflake_load.sql` stages the pack in Snowflake.

## The 10 sites

| Site | Name | Structure | Scope | RFDS | CDs | Vendor meas. | Seeded issues |
|---|---|---|---|---|---|---|---|
| TXDA1024 | Lakewood Heights | 150 ft monopole | C-band add | XLSX v2 | DXF+PDF | Yes | 2 |
| TXFW2217 | Fossil Creek | 180 ft self-support | C-band add | XLSX v2 | DXF+PDF | Yes | 2 |
| TXPL0588 | Legacy Drive | 125 ft monopole | n41 add + low-band refresh | XLSX v2 | DXF+PDF | Yes | 3 |
| TXIR1340 | Valley Ranch | 140 ft monopole | C-band add | XLSX v2 | PDF only | Yes | 2 |
| TXGR0719 | Arbor Bend | 195 ft self-support | Full modernization | XLSX v3 | DXF+PDF | Yes | 3 |
| TXDE0831 | Hickory Flats | 220 ft guyed | n41 add + low-band refresh | XLSX v3 | DXF+PDF | No | 2 |
| TXRI0906 | Collins Tower | Rooftop, 4 sectors | C-band add + new sector | XLSX v3 | DXF+PDF | No | 2 |
| TXMK1112 | Lake Forest | 165 ft monopole | Full modernization | PDF | DXF+PDF | No | 2 |
| TXAD0405 | Uptown Plaza | Rooftop, 2 sectors | n41 add + low-band refresh | PDF | PDF only | No | 2 |
| TXCA0977 | Carrollton Station | 110 ft monopole | C-band add | PDF | DXF+PDF | No | 2 |

## Seeded discrepancies (22) — what the POC should catch

Full list with expected action and BOM impact: `answer_key/seeded_discrepancies.csv`.

- **CD vs field (8):** missing spare pipe, unrecorded legacy RRU, unrecorded legacy antenna, antennas 4 ft lower than drawn, azimuth 12 deg off, no roof sled where CDs show one, cable route 40 ft longer / 27 ft shorter than the CD (changes trunk length).
- **RFDS vs CD (3):** azimuth mismatch, radio on RFDS missing from CDs, AAU position swapped.
- **REV 0 BOM errors (8):** missing ground kit, duplicate line, wrong RF jumper qty, non-approved P/N, hangers sized for wrong trunk, missing breakers, one trunk instead of two, missing weatherproofing.
- **MA/SA (3):** reinforcement kits required on two sites; one structure fails at 103%.

## How the data fits together

- **RFDS governs RF.** Where RFDS and CDs disagree, the final BOM follows the RFDS and the issue becomes an RFI.
- **Drone = site as found, before construction.** It shows existing equipment only. Findings are reconciled against the CDs' existing conditions and against where new equipment must mount.
- **Final BOM = rules applied to the corrected site** (RFDS config + field conditions + MA requirements). The rules engine in `reference/bom_rules.xlsx` reproduces every line in `answer_key/final_engineer_BOM_REV1.xlsx`; each line carries its rule ID and source document.
- **REV 0 = rules applied to the CDs as drawn,** plus the seeded tool errors. `answer_key/rev0_vs_final_diff.csv` lists every quantity change.
- **Trunk length** = next catalog step (100–350 ft) at or above 1.10 x (vertical + horizontal run). Tower vertical = highest new radio/AAU rad center + 5 ft; rooftop uses the riser run.

## Conventions

- **Point cloud:** local ENU metres, origin at the structure centreline at grade; +X east, +Y north, +Z up; azimuth clockwise from +Y. Site lat/long in each `*_capture_metadata.json`.
- **Classification codes:** 1 unclassified, 2 ground, 6 building, 14 guy wire, 15 tower, 64 antenna/AAU, 65 radio, 66 mount/pipe/sled, 67 cable, 68 cabinet. Codes 64–68 are user-defined; drop them if you want the POC to segment from scratch. `answer_key/pointcloud_truth_objects.csv` has the true object boxes either way.
- **Sectors:** A/B/C/D = Alpha/Beta/Gamma/Delta. Statuses: Existing/Retain, New/Add, Remove.
- **Sitetracker IDs** are 18-character Salesforce-style but synthetic; field API names need mapping to Ericsson's org.

## Known limits of synthetic data

- **AutoCAD** files are DXF, not DWG. DXF is AutoCAD's exchange format and carries the same layers and block attributes. Convert with the free ODA File Converter if the POC must ingest DWG.
- **CD PDFs** carry text as vector outlines, like many CAD exports. They have no text layer, so extraction needs OCR or layout AI. RFDS and MA/SA PDFs have real text.
- **Imagery and video** are renders of the point cloud, not photographs. Equipment labels are not legible, so label reading (model ID from photos) cannot be tested with this pack.
- **Configurations are Ericsson-typical but simplified:** one radio pairing pattern per scope type and no tower-mounted amplifiers, diplexers or combiners.
