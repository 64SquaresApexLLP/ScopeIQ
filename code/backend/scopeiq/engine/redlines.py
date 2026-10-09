"""Pipeline step 7 (draft side) - Redlines and RFIs drafted from discrepancies.

A redline is the markup the A&E must apply to a drawing (sheet, from -> to, the text written on the sheet).
An RFI is a question to the party that owns the answer: RF questions (RFDS vs CD, unrecorded equipment,
azimuth/rad center in the field) go to Ericsson's RF engineer; drawing questions go to the A&E.
Both stay DRAFT until a person submits them through the workflow.
"""
from __future__ import annotations

from scopeiq.common.ids import stable_id
from scopeiq.common.logging import get_logger, log_call
from scopeiq.domain import SECTOR_NAMES, Discrepancy, Redline, Rfi, SiteFacts
from scopeiq.reference.loader import ReferenceData

log = get_logger(__name__)


def _sec(s):
    return SECTOR_NAMES.get(s or "", "SITE").upper()


def _model(ref, k):
    return ref.catalog.get(k).model.upper() if k and k in ref.catalog else str(k or "").upper()


def _markup(d: Discrepancy, f: SiteFacts, ref: ReferenceData) -> tuple[str, str, str, str] | None:
    """(sheet, markup text, change_from, change_to) for a discrepancy, or None if it does not touch a drawing."""
    r, s, p = d.rule_id, _sec(d.sector), d.position
    flight = (f.site.get("pointcloud_stats") or {}).get("flight_date", "")
    if r == "FLD-02":
        return "A-3", f"DELETE (E) SPARE PIPE AT {s} POS {p} - NOT PRESENT PER DRONE SURVEY. ADD (P) MOUNT PIPE IF POSITION IS USED.", "(E) pipe", "none / (P) pipe"
    if r == "FLD-05":
        return "A-3", f"(E) ROOF SLED AT {s} NOT PRESENT PER DRONE SURVEY - REVISE TO (P) NON-PENETRATING ROOF SLED.", "(E) roof sled", "(P) roof sled"
    if r == "FLD-06":
        return "A-4", (f"REVISE CABLE SCHEDULE HORIZ RUN {d.expected:g} FT -> {d.found:.0f} FT (MEASURED). RECOMPUTE REQ'D LENGTH AND SPECIFIED TRUNK."
                       ), f"{d.expected:g} ft", f"{d.found:.0f} ft"
    if r == "FLD-03":
        old, new = "/".join(f"{float(x):g}" for x in d.expected), "/".join(f"{float(x):g}" for x in d.found)
        return "A-2", f"REVISE RAD CENTER OF EXISTING ANTENNAS {old} FT -> {new} FT (MEASURED).", f"{old} ft", f"{new} ft"
    if r == "FLD-04":
        return "A-3", f"EXISTING {s} MEASURED AT {d.found:.0f} DEG (DRAWN {d.expected:g} DEG). SHOW RE-ORIENTATION TO DESIGN AZIMUTH.", f"{d.expected:g} deg", f"{d.found:.0f} deg"
    if r == "FLD-01":
        return "A-3", f"ADD UNRECORDED (E) {_model(ref, d.found)} AT {s} POS {p} TO EXISTING INVENTORY AND MARK (R) REMOVE.", "not shown", f"(E)/(R) {d.found}"
    if r == "FLD-07":
        return "A-3", f"(E) {_model(ref, d.expected)} AT {s} POS {p} NOT FOUND IN FIELD - CONFIRM AND REVISE INVENTORY.", f"(E) {d.expected}", "not found"
    if r == "RFC-01":
        return "A-3", f"REVISE {s} AZIMUTH {d.found:g} -> {d.expected:g} DEG PER RFDS {f.rfds_revision} (SUBJECT TO RFI).", f"{d.found:g} deg", f"{d.expected:g} deg"
    if r == "RFC-02":
        return "A-3", f"ADD (P) {_model(ref, d.expected)} AT {s} POS {p} PER RFDS {f.rfds_revision}; UPDATE A-4 SCHEDULE AND T-1 SCOPE.", "not shown", f"(P) {d.expected}"
    if r == "RFC-03":
        return "A-3", f"DELETE (P) {_model(ref, d.found)} AT {s} POS {p} - NOT ON RFDS {f.rfds_revision}.", f"(P) {d.found}", "deleted"
    if r == "RFC-04":
        moves = "; ".join(f"{_model(ref, k)} TO POS {'/'.join(map(str, v))}" for k, v in (d.expected or {}).items())
        pos = lambda m: "; ".join(f"{_model(ref, k)} pos {'/'.join(map(str, v))}" for k, v in (m or {}).items())  # noqa: E731
        return "A-3", f"REVISE {s} POSITIONS PER RFDS {f.rfds_revision}: {moves}.", pos(d.found), pos(d.expected)
    if r == "RFC-05":
        return "A-2", f"REVISE {s} RAD CENTER TO RFDS VALUES {d.expected}.", str(d.found), str(d.expected)
    if r == "MNT-01":
        kits = ", ".join(f"{_sec(m['sector'])} {m['kit_key']} x{m['qty']}" for m in d.expected or [])
        return "A-3", f"ADD MOUNT REINFORCEMENT PER {f.ma.report_id if f.ma else 'MA'}: {kits}. ADD TO T-1 SCOPE OF WORK.", "not shown", kits
    if r == "REV-02":
        return "T-1", f"UPDATE NOTE 'RF CONFIGURATION PER RFDS {d.found}' TO RFDS {d.expected}; REVISE DRAWINGS ACCORDINGLY.", d.found, d.expected
    if r == "LOAD-01":
        return "MA", "RE-RUN MOUNT ANALYSIS ON FINAL RFDS LOADING.", "analysed loading", "final RFDS loading"
    return None


RFI_TO = {"RFC-01": "ERICSSON", "RFC-02": "ERICSSON", "RFC-03": "ERICSSON", "RFC-04": "ERICSSON", "RFC-06": "ERICSSON", "FLD-01": "ERICSSON",
          "FLD-03": "AE_ENGINEER", "FLD-04": "ERICSSON", "FLD-07": "AE_ENGINEER", "REV-01": "AE_ENGINEER", "DOC-01": "ERICSSON",
          "CBL-01": "AE_ENGINEER", "SA-01": "ERICSSON"}


def _rfi_text(d: Discrepancy, f: SiteFacts) -> tuple[str, str]:
    r = d.rule_id
    if r == "RFC-01":
        return (f"RFDS {f.rfds_revision} sets {SECTOR_NAMES.get(d.sector)} to {d.expected:g} deg; the CD (and field) show {d.found:g} deg. "
                "Please confirm the re-orientation is intended."), f"Confirm {d.expected:g} deg per RFDS; CD to be redlined and re-orientation added to SoW."
    if r == "FLD-01":
        return (f"The drone survey found {d.found} at {SECTOR_NAMES.get(d.sector)} position {d.position}, which is not on the RFDS or the CD. "
                "Please confirm it should be removed (or reused)."), "Remove; removal line added to the BOM."
    if r == "FLD-04":
        return (f"{SECTOR_NAMES.get(d.sector)} antennas measure {d.found:.0f} deg in the field vs {d.expected:g} deg designed. "
                "Please confirm re-orientation to the design azimuth."), "Re-orient to design azimuth during construction."
    if r == "FLD-03":
        return (f"Existing antennas measure {d.found} ft rad center vs {d.expected} ft on the CD/RFDS. Please confirm and revise the elevation."), \
            "Revise CD A-2 to measured rad centers."
    return d.description, d.bom_impact or ""


@log_call()
def draft_redlines_and_rfis(facts: SiteFacts, discrepancies: list[Discrepancy], ref: ReferenceData) -> tuple[list[Redline], list[Rfi]]:
    redlines, rfis = [], []
    for d in discrepancies:
        if d.outcome in ("REDLINE", "RFI") and d.target_doc in ("CD", "MA_SA"):
            mk = _markup(d, facts, ref)
            if mk:
                sheet, text, frm, to = mk
                doc_type = "MA_SA" if sheet == "MA" else "CD"
                rev = facts.cd_revision if doc_type == "CD" else (facts.ma.report_id if facts.ma else "")
                redlines.append(Redline(stable_id("RDL", d.disc_id), facts.site_id, doc_type, rev, sheet, d.disc_id, text, str(frm), str(to)))
        if d.outcome in ("RFI", "ESCALATE"):
            q, a = _rfi_text(d, facts)
            rfis.append(Rfi(stable_id("RFI", d.disc_id), facts.site_id, RFI_TO.get(d.rule_id, "AE_ENGINEER"), f"{facts.site_id}: {d.title}", q, a, [d.disc_id]))
    log.info("drafted %d redline(s), %d RFI(s)", len(redlines), len(rfis), extra={"site_id": facts.site_id})
    return redlines, rfis
