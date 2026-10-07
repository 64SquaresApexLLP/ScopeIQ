# Test results

Run: `cd code/backend && python -m pytest` - **19 passed** (about 45 s; it runs the full pipeline on all ten sample sites twice,
once for the acceptance checks and once on a separate database for the API tests).

The data generator in `Data/DataDetails/generator` is the answer key: it holds the 22 seeded issues and the true BOM
for every site. The tests compare ScopeIQ's output with it.

| Test file | What it proves |
|---|---|
| `tests/test_seeded_issues.py` | all 22 seeded issues are detected by the right rule, sector and part; no unexpected findings; the generated REV 1 BOM equals the true BOM for every site; every REV 0 difference is classified as a tool error; redlined PDFs and packages are written |
| `tests/test_units.py` | rule expressions are evaluated safely; OCR text resolves to catalog items; trunk length steps; a missing route is never assumed; workflow enforces roles and reason codes; human edits need a reason; logging levels follow the environment |
| `tests/test_api.py` | health and auth; site list and detail; a CX SP sees only its own sites; discrepancy workflow (reason/comment rules, role denial, comments, audit); BOM edit then approve then edit refused (`SIQ-LOCK-409`); Excel export; redlined PDF served; admin-only endpoints refused; upload validation |

## Seeded issues: 22 of 22 detected

| Seeded issue | What was planted | Rule | ScopeIQ finding | Outcome |
|---|---|---|---|---|
| TXDA1024-01 | CD A-3 shows an existing spare pipe at Beta position 3; drone survey shows no pipe. | FLD-02 | Beta position 3 existing spare pipe missing in field | REDLINE |
| TXDA1024-02 | REV 0 omits the ground kit for the new Gamma AAU. | BOM-01 | GK-6-TW missing from REV 0 (Gamma) | BOM_CHANGE |
| TXFW2217-01 | RFDS sets Alpha azimuth to 30 deg; CDs (and field) show 20 deg. | RFC-01 | Alpha azimuth RFDS 30 vs CD 20 | RFI |
| TXFW2217-02 | REV 0 lists the Alpha SFP28 25G line twice. | BOM-03 | Duplicate SFP28 25G LR line (Alpha) | BOM_CHANGE |
| TXPL0588-01 | Unrecorded legacy RRUS 11 B12 on Gamma position 1 pipe; not on RFDS or CDs. | FLD-01 | Unrecorded radio at Gamma position 1 | RFI |
| TXPL0588-02 | REV 0 carries 2 RF jumpers per Radio 4480 instead of 4 (4 ports). | BOM-02 | RFJ-43-6 quantity differs (Alpha, Beta, Gamma) | BOM_CHANGE |
| TXPL0588-03 | Mount analysis passes only with reinforcement kits on all three sectors; REV 0 omits them. | MNT-01 | MA modifications not shown on CD | REDLINE |
| TXIR1340-01 | Existing antennas measured at 131 ft rad center; CDs and RFDS show 135 ft. | FLD-03 | Existing antennas measured 4 ft lower than drawn | RFI |
| TXIR1340-02 | REV 0 uses a non-approved fiber jumper (AF-LC-15) for the AAUs. | BOM-04 | Non-approved AF-LC-15 used instead of FJ-LCLC-OD-20 | BOM_CHANGE |
| TXGR0719-01 | RFDS adds Radio 4460 B2 B66 at Beta position 1; CDs omit it. | RFC-02 | Beta Radio 4460 B2 B66 on RFDS, not on CD | RFI |
| TXGR0719-02 | Measured cabinet-to-tower route is 80 ft; CD cable schedule uses 40 ft. | FLD-06 | Cable route measured 80 ft, CD 40 ft | REDLINE |
| TXGR0719-03 | Structural analysis at 103% of capacity (FAIL). | SA-01 | Structure fails SA at 103% | ESCALATE |
| TXDE0831-01 | Alpha antennas measured at 348 deg; RFDS and CDs specify 0 deg (12 deg off). | FLD-04 | Alpha measured at 348 deg, CD 0 deg | RFI |
| TXDE0831-02 | REV 0 sizes hangers for a 250 ft trunk; the specified trunk is 300 ft. | BOM-02 | SNAP-3S quantity differs (Site) | BOM_CHANGE |
| TXRI0906-01 | CDs show an existing roof sled for new Delta sector; roof has none. | FLD-05 | Delta roof sled not found in field | REDLINE |
| TXRI0906-02 | REV 0 omits the 60 A DC breakers for all four AAUs. | BOM-01 | DCB-60A missing from REV 0 (Alpha, Beta, Delta, Gamma) | BOM_CHANGE |
| TXMK1112-01 | Unrecorded legacy APXV antenna on a third Gamma pipe; not on RFDS or CDs. | FLD-01 | Unrecorded antenna at Gamma position 3 | RFI |
| TXMK1112-02 | REV 0 carries one hybrid trunk for 12 new powered devices (needs 2). | BOM-02 | REV 0 trunk count 1 vs 2 required | BOM_CHANGE |
| TXAD0405-01 | RFDS places the Beta AIR 6419 at position 3; CDs show it at position 2 (swapped with the new NNH4). | RFC-04 | Beta positions differ RFDS vs CD | RFI |
| TXAD0405-02 | REV 0 omits all weatherproofing kits. | BOM-01 | WPK-UNIV missing from REV 0 (Alpha, Beta, Site) | BOM_CHANGE |
| TXCA0977-01 | Measured cabinet-to-tower route is 18 ft; CD cable schedule uses 45 ft. | FLD-06 | Cable route measured 18 ft, CD 45 ft | REDLINE |
| TXCA0977-02 | Mount analysis requires a reinforcement kit on Alpha; REV 0 omits it. | MNT-01 | MA modifications not shown on CD | REDLINE |

Outcome is what the finding asks for: REDLINE (fix the drawing), RFI (question to Ericsson/A&E), BOM_CHANGE (REV 1 differs
from REV 0), ESCALATE (outside BOM scope, e.g. SA fail), REVIEW (human check).

## BOM accuracy

For every site the generated REV 1 equals the generator's true BOM line for line (sector, part, action, quantity),
with one documented exception: on TXMK1112 (point cloud only) the unrecorded legacy antenna is identified as a
dimensional look-alike (APXV vs SBNHH). The removal line is created and the finding is flagged for review with both
candidate models listed.

Running the same rules on the CD *as drawn* reproduces the received REV 0 except where REV 0 itself is wrong, which
is how REV 0 errors (BOM-01 to BOM-05) are separated from field and document changes. Each REV 0 to REV 1 change carries
a reason code: RC-REV0-ERR (tool error), RC-FIELD-COND (field condition), RC-MA-REQ (mount analysis), RC-DOC-CONFLICT
(RFDS over CD).

## Findings beyond the seeded list

| Site | Rule | Finding | Assessment |
|---|---|---|---|
| TXAD0405 | FLD-03 | Existing antennas measured 5 ft higher than drawn (68 ft vs 63 ft rooftop rad center) | Real in the synthetic data: the point cloud places the rooftop antennas at 68 ft. Not seeded, but correct to flag. |
| all sites | EXT-01 | n value(s) need review in a document | By design: every value read below the confidence threshold (0.80) or not matched to the catalog is queued once per document for a human to confirm (OCR'd CD fields, point-cloud model guesses, vendor rows without a model). |

## Current output (fresh run, environment `test`)

| Site | Stream | Structure | Findings | High | Redlines | REV 0 to REV 1 changes | Cycle days | Estimate (illustrative) |
|---|---|---|---|---|---|---|---|---|
| TXAD0405 | DEPLOYMENT | Rooftop | 5 | 0 | 2 | 3 | 6.6 | $131,487 |
| TXCA0977 | BOM | Monopole | 3 | 1 | 2 | 4 | 4.3 | $154,844 |
| TXDA1024 | BOM | Monopole | 2 | 0 | 1 | 2 | 4.0 | $154,451 |
| TXDE0831 | DEPLOYMENT | Guyed tower | 3 | 0 | 1 | 1 | 6.6 | $180,928 |
| TXFW2217 | BOM | Self-support tower | 3 | 1 | 1 | 1 | 4.0 | $155,904 |
| TXGR0719 | BOM | Self-support tower | 4 | 2 | 2 | 13 | 34.0 | $390,012 |
| TXIR1340 | BOM | Monopole | 3 | 1 | 1 | 6 | 4.0 | $153,866 |
| TXMK1112 | BOM | Monopole | 3 | 1 | 1 | 9 | 14.2 | $386,766 |
| TXPL0588 | DEPLOYMENT | Monopole | 4 | 2 | 2 | 7 | 8.7 | $188,284 |
| TXRI0906 | BOM | Rooftop | 3 | 0 | 1 | 5 | 6.0 | $200,531 |

Stored redlines for each site are in `output/sites/<SITE>/redlines/`: the red-marked CD PDF (summary sheet plus numbered
markups on the affected sheets), and JSON/CSV of the discrepancies, redlines and RFIs. The REV 1 workbook (same columns
as the REV 0 tool export plus parent, reason code and a "Changes vs REV 0" sheet) is in `output/sites/<SITE>/`.

## Known limitations

| Area | Limitation | Mitigation in the POC |
|---|---|---|
| Scanned CDs (TXAD0405, TXIR1340 have PDF only) | OCR reads schedules and azimuths but not spare-pipe or frame graphics; pipes are inferred at scheduled positions and flagged | values below threshold go to EXT-01 review; DXF is preferred whenever present |
| Point cloud | rooftop cable route cannot be measured (no vertical run to separate) | route held, CBL-01 raised instead of assuming a length |
| Point cloud | antenna/radio models identified by dimensions only; look-alikes (APXV/SBNHH, RRUS 11/R2217) are ambiguous | confidence halved, both candidates listed, finding needs review |
| Drone imagery | labels on equipment are not legible in the synthetic photos | imagery used as evidence frames, not for model reading |
| Video | frames are chosen by sharpness and bearing; no object detection on video | best frame per sector attached to findings |
| Estimates | rate card and cycle-time parameters are illustrative | values live in `reference_data/rate_card.csv` and `cycle_time_params.csv` |
| Snowflake | scripts syntax-checked (sqlglot, 277 statements) but not executed against a live account | see `snowflake/EXECUTION_GUIDE.md` section 7 |
| Mobile app | tested as a web build in Chromium (scoper and CX SP flows); not yet run on a physical iOS/Android device | Expo Go instructions in INSTALL.md |
