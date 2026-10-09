"""
grounding.py - Number validator for generated text (Ideation #14, used by the #45 copilot).

Code computes every statistic; a language model may only write narrative around them. Before any generated
sentence is shown, every number in it must be a value from the facts bundle (or a plain unit conversion of
one: ratio -> percent, m² -> ha / km²), at the precision it is written with. Sentences that fail are dropped,
never shown. web/copilot.js implements the same rule for the console.
"""

import re
from typing import Any, Dict, Iterable, List, Set

# digits not glued to a word or a decimal point (so CHG_0001 and v2 are not numbers); thousands separators ok
NUM = re.compile(r"(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def numbers_in(text: str) -> List[str]:
    # a score written "92/100" is one number: the scale is not a claim
    return [m.group(0) for m in NUM.finditer(re.sub(r"/\s*100\b", "", text))]


def _value(tok: str) -> float:
    return float(tok.replace(",", "").replace("−", "-"))


def _decimals(tok: str) -> int:
    return len(tok.split(".")[1]) if "." in tok else 0


def allowed_values(facts: Any) -> Set[float]:
    """Every number in the facts (numeric fields and numbers written inside strings) with its conversions."""
    out: Set[float] = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            out.update({float(v), v * 100.0, v / 100.0, v / 1e4, v / 1e6, abs(v), abs(v) * 100.0})
        elif isinstance(v, str):
            for tok in numbers_in(v):
                x = _value(tok)
                out.update({x, abs(x)})
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(facts)
    return out


def supported(tok: str, allowed: Iterable[float]) -> bool:
    """tok is a rounding of an allowed value at the precision tok is written with (16,300 ~ 16300.0, 96 ~ 96.4)."""
    x, tol = abs(_value(tok)), 0.5 * 10 ** -_decimals(tok) + 1e-9
    return any(abs(x - abs(a)) <= tol for a in allowed)


def check(text: str, facts: Any) -> Dict[str, Any]:
    allowed = allowed_values(facts)
    bad = [t for t in numbers_in(text) if not supported(t, allowed)]
    return {"ok": not bad, "unverified": bad}


def keep_grounded(items: List[str], facts: Any) -> Dict[str, Any]:
    """Splits generated sentences into those whose numbers all check out and those that are dropped."""
    allowed = allowed_values(facts)
    kept, dropped = [], []
    for s in items:
        (kept if all(supported(t, allowed) for t in numbers_in(s)) else dropped).append(s)
    return {"kept": kept, "dropped": dropped}


if __name__ == "__main__":
    facts = {"id": "CHG_0001", "area_sqm": 16300.0, "magnitude": 0.964, "exposure": "389 m from Rushikul Vidyalaya (school)",
             "first_seen": "2021-01-27", "d_ndvi": -0.34, "comparability": {"score": 92}}
    assert numbers_in("CHG_0001 covers 16,300 m² (1.63 ha)") == ["16,300", "1.63"]
    assert check("16,300 m², 1.63 ha, 96% confidence, 389 m from a school, first seen 2021", facts)["ok"]
    assert check("NDVI fell by 0.34; comparability 92/100", facts)["ok"]
    assert check("Score is 0.96", facts)["ok"]                         # 0.964 at two decimals
    r = check("About 450 m from a school and 3 hospitals nearby", facts)
    assert r["unverified"] == ["450", "3"], r
    assert not check("area 16,400 m²", facts)["ok"]                    # off by more than the written precision
    k = keep_grounded(["Area is 16,300 m².", "It grew 40% since 2019."], facts)
    assert k["kept"] == ["Area is 16,300 m²."] and len(k["dropped"]) == 1
    print("grounding self-check ok")
