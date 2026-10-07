"""Material catalog library: lookups by catalog key, model, manufacturer or customer P/N, plus tolerant model
matching for text read by OCR / AI extraction (different A&E firms write model names differently)."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from scopeiq.common.errors import ReferenceDataError

KIND_BY_SUBCATEGORY = {"Active Antenna (AAU)": "air", "Remote Radio": "radio", "Passive Antenna": "passive", "Baseband": "baseband"}


def norm(text: str) -> str:
    """Normalise model text: upper case, drop spaces/dashes/dots, map common OCR confusions."""
    t = re.sub(r"[\s\-_./]", "", str(text or "").upper())
    return t.replace("O", "0").replace("I", "1").replace("S", "5").replace("B", "8")


@dataclass
class CatalogItem:
    key: str
    category: str
    subcategory: str
    manufacturer: str
    model: str
    mfr_pn: str
    customer_pn: str
    description: str
    uom: str
    supply: str
    approved: bool
    unit_cost: float
    rf_ports: int
    power_w: float
    bands: str
    technology: str
    height_m: float
    width_m: float
    depth_m: float
    aliases: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return KIND_BY_SUBCATEGORY.get(self.subcategory, "other")

    @property
    def is_major(self) -> bool:
        return self.category == "Major Equipment"


class Catalog:
    def __init__(self, items: list[CatalogItem]):
        self.items = {i.key: i for i in items}
        self._by_model = {i.model.upper(): i for i in items}
        self._norm: dict[str, CatalogItem] = {}
        for i in items:
            for name in [i.model, i.mfr_pn, i.customer_pn, i.key, *i.aliases]:
                if name:
                    self._norm.setdefault(norm(name), i)

    def __contains__(self, key: str) -> bool:
        return key in self.items

    def get(self, key: str) -> CatalogItem:
        try:
            return self.items[key]
        except KeyError as exc:
            raise ReferenceDataError(f"Catalog key {key!r} not found", details={"key": key}) from exc

    def by_model(self, model: str) -> CatalogItem | None:
        return self._by_model.get(str(model or "").strip().upper())

    def by_part_number(self, pn: str) -> CatalogItem | None:
        pn = str(pn or "").strip().upper()
        if not pn:
            return None
        return next((i for i in self.items.values() if pn in (i.mfr_pn.upper(), i.customer_pn.upper())), None)

    def resolve(self, text: str, *, kinds: tuple[str, ...] | None = None, cutoff: float = 0.82) -> tuple[CatalogItem | None, float]:
        """Best catalog item for free text with a 0..1 match score (1.0 = exact)."""
        if not text:
            return None, 0.0
        exact = self.by_model(text)
        if exact and (not kinds or exact.kind in kinds):
            return exact, 1.0
        n = norm(text)
        pool = {k: v for k, v in self._norm.items() if not kinds or v.kind in kinds}
        if n in pool:
            return pool[n], 0.97
        best = difflib.get_close_matches(n, list(pool), n=1, cutoff=cutoff)
        if not best:
            return None, 0.0
        return pool[best[0]], round(difflib.SequenceMatcher(None, n, best[0]).ratio(), 3)

    def keys_of_kind(self, kind: str) -> list[str]:
        return [k for k, v in self.items.items() if v.kind == kind]

    def trunk_keys(self) -> list[str]:
        return sorted((k for k, v in self.items.items() if v.subcategory == "Hybrid Trunk"), key=lambda k: int(re.sub(r"\D", "", k)))
