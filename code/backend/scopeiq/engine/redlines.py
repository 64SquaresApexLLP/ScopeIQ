"""Pipeline stage 4 - Redlines and RFIs: first DECIDE, then draft.

Stage 3 leaves a list of mismatches. This stage decides, for every one of them, whether the CD drawing has to be
marked up and whether somebody has to be asked a question, and only then drafts what the decision calls for. If no
mismatch touches the drawing, no redlined drawing is produced.

A finding gets a REDLINE (a markup on the CD drawing) when ALL of these hold:
  1. it is still live: a reviewer has not dismissed it and it has not been resolved;
  2. its rule names a document that can be marked up (the CD drawing, or the MA/SA report);
  3. its rule outcome calls for a drawing change (REDLINE), or for a question whose answer changes the drawing (RFI, then the
     markup is drafted as 'subject to the RFI'); outcomes FLAG / REVIEW / ESCALATE / BOM_CHANGE never mark the drawing;
  4. a markup is defined for the rule (what to write on which sheet).

A finding gets an RFI when its rule outcome is RFI or ESCALATE: the documents cannot settle it, a person outside ScopeIQ
(Ericsson's RF engineer, the A&E, the structural engineer) has to confirm or answer. The RFI is drafted here, right
after the findings exist, and stays DRAFT until a person submits it through the workflow; the site is put on hold
while a blocking RFI is open. The answer comes back as the RFI being ANSWERED and the finding being resolved.

A redlined drawing is written only when at least one live finding marks up the CD drawing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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


# --------------------------------------------------------------------------- the decision
CLOSED_STATES = {"DISMISSED", "RESOLVED", "CLOSED"}           # a person (or a corrected document) already settled these
MARKABLE = ("CD", "MA_SA")                                      # documents a redline can be written against
REDLINE_OUTCOMES = {"REDLINE": "REQUIRED", "RFI": "SUBJECT_TO_RFI"}
RFI_OUTCOMES = ("RFI", "ESCALATE")


@dataclass
class FindingDecision:
    disc_id: str
    rule_id: str
    title: str
    redline: str                 # REQUIRED | SUBJECT_TO_RFI | NONE
    redline_reason: str
    rfi: bool
    rfi_reason: str
    on_cd_drawing: bool          # the markup goes on the CD drawing (not on the MA/SA report)


@dataclass
class RedlineDecision:
    required: bool               # write a redlined CD drawing
    reason: str
    findings_checked: int
    items: list[FindingDecision] = field(default_factory=list)

    @property
    def redline_count(self) -> int:
        return sum(1 for i in self.items if i.redline != "NONE")

    @property
    def rfi_count(self) -> int:
        return sum(1 for i in self.items if i.rfi)

    def to_dict(self) -> dict:
        return {"required": self.required, "reason": self.reason, "findings_checked": self.findings_checked,
                "redlines": self.redline_count, "rfis": self.rfi_count, "items": [i.__dict__ for i in self.items]}


def _safe_markup(d: Discrepancy, f: SiteFacts, ref: ReferenceData):
    try:
        return _markup(d, f, ref)
    except Exception:  # noqa: BLE001 - a finding with odd values must not stop the others
        log.exception("markup for %s failed", d.rule_id, extra={"site_id": f.site_id})
        return None


def decide(facts: SiteFacts, discrepancies: list[Discrepancy], ref: ReferenceData) -> RedlineDecision:
    """Stage 4's decision: which findings mark up a drawing, which need a question, and whether a redlined drawing is needed at all."""
    items: list[FindingDecision] = []
    for d in discrepancies:
        live = d.status not in CLOSED_STATES
        markup = _safe_markup(d, facts, ref) if live and d.outcome in REDLINE_OUTCOMES and d.target_doc in MARKABLE else None
        if not live:
            redline, why = "NONE", f"already {d.status.lower()} - nothing to mark up"
        elif d.target_doc not in MARKABLE:
            redline, why = "NONE", "it does not name a drawing to mark up (the finding is raised for review, not for a change)" if d.target_doc in ("ANY", "REGISTRY", "") else f"it concerns the {d.target_doc.replace('_', ' ').lower()}, not a drawing"
        elif d.outcome not in REDLINE_OUTCOMES:
            redline, why = "NONE", f"outcome is {d.outcome.replace('_', ' ').lower()}: it does not change the drawing"
        elif markup is None:
            redline, why = "NONE", f"no drawing markup is defined for {d.rule_id}"
        elif d.outcome == "REDLINE":
            redline, why = "REQUIRED", f"{d.rule_id} is a drawing mismatch: the {d.target_doc} must be corrected"
        else:
            redline, why = "SUBJECT_TO_RFI", f"{d.rule_id} needs an answer first; the markup is drafted as 'subject to the RFI'"
        asks = live and d.outcome in RFI_OUTCOMES
        party = {"ERICSSON": "Ericsson", "AE_ENGINEER": "the A&E engineer"}.get(RFI_TO.get(d.rule_id, "AE_ENGINEER"), "the A&E engineer")
        rfi_why = (f"{d.rule_id} cannot be settled from the documents: {party} has to answer" if asks
                   else ("already settled" if not live else "the documents settle it: no question needed"))
        items.append(FindingDecision(d.disc_id, d.rule_id, d.title, redline, why, asks, rfi_why,
                                     on_cd_drawing=redline != "NONE" and d.target_doc == "CD"))
    on_drawing = [i for i in items if i.on_cd_drawing]
    if on_drawing:
        reason = f"{len(on_drawing)} finding(s) change the CD drawing ({', '.join(sorted({i.rule_id for i in on_drawing}))}): a redlined drawing is needed"
    elif not discrepancies:
        reason = "No mismatch was found: the sources agree, so no redlined drawing is needed"
    else:
        reason = f"{len(discrepancies)} finding(s) were raised but none of them changes the CD drawing: no redlined drawing is needed"
    return RedlineDecision(bool(on_drawing), reason, len(discrepancies), items)


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
def draft_redlines_and_rfis(facts: SiteFacts, discrepancies: list[Discrepancy], ref: ReferenceData,
                            decision: RedlineDecision | None = None) -> tuple[list[Redline], list[Rfi]]:
    """Draft only what the decision calls for."""
    decision = decision or decide(facts, discrepancies, ref)
    by_id = {i.disc_id: i for i in decision.items}
    redlines, rfis = [], []
    for d in discrepancies:
        verdict = by_id.get(d.disc_id)
        if not verdict:
            continue
        if verdict.redline != "NONE":
            mk = _safe_markup(d, facts, ref)
            if mk:
                sheet, text, frm, to = mk
                doc_type = "MA_SA" if sheet == "MA" else "CD"
                rev = facts.cd_revision if doc_type == "CD" else (facts.ma.report_id if facts.ma else "")
                redlines.append(Redline(stable_id("RDL", d.disc_id), facts.site_id, doc_type, rev, sheet, d.disc_id, text, str(frm), str(to)))
        if verdict.rfi:
            q, a = _rfi_text(d, facts)
            rfis.append(Rfi(stable_id("RFI", d.disc_id), facts.site_id, RFI_TO.get(d.rule_id, "AE_ENGINEER"), f"{facts.site_id}: {d.title}", q, a, [d.disc_id]))
    log.info("drafted %d redline(s), %d RFI(s)", len(redlines), len(rfis), extra={"site_id": facts.site_id})
    return redlines, rfis
