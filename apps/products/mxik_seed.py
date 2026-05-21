"""
Hard-coded MXIK suggestion seed for the typeahead validator.

In production this is backed by pgvector similarity over the official
MXIK catalogue (300K+ codes). For the MVP we use the 15 codes the
mock data already references, plus a handful of variations.
"""

from __future__ import annotations

import random

MXIK_SEED: tuple[tuple[str, str], ...] = (
    ("0201301000", "Mol go'shti, premium kategoriya"),
    ("0201302000", "Mol go'shti, ikkinchi nav"),
    ("0202309000", "Qo'y go'shti, muzlatilgan"),
    ("0207120000", "Tovuq go'shti, butun"),
    ("0401200000", "Sut, pasterizovannoy 1-6%"),
    ("0405100000", "Sariyog'"),
    ("0406100000", "Pishloq, yangi"),
    ("0902100000", "Yashil choy, qadoqlangan ≤3kg"),
    ("0902200000", "Qora choy, qadoqlangan ≤3kg"),
    ("0902409000", "Choy yaproq, qora — boshqalar"),
    ("1512190000", "Kungaboqar yog'i, rafinirovaniya"),
    ("1701991000", "Oq shakar, qadoqlangan"),
    ("1905900000", "Non va non mahsulotlari"),
    ("2201100000", "Mineral suv va gazirovkasiz suv"),
    ("2202100000", "Gazlangan ichimliklar, qadoqlangan"),
    ("2402200000", "Sigaret, tutun bilan"),
)


def search(q: str, limit: int = 10) -> list[dict]:
    """Case-insensitive substring match on name OR code prefix.

    Confidence is randomised in [0.6, 0.95] for demo determinism per
    code (seeded with the query+code hash) so repeated calls return
    consistent ranking.
    """
    q = (q or "").strip().lower()
    if not q:
        return []
    rng = random.Random(q)
    results: list[dict] = []
    for code, name in MXIK_SEED:
        if q in name.lower() or code.startswith(q):
            confidence = round(rng.uniform(0.6, 0.95), 2)
            results.append({"code": code, "name": name, "confidence": confidence})
    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results[:limit]
