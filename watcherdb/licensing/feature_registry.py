"""
Runtime feature registry populated from `LicenseClaims.features`.

The rest of the code base reads this registry rather than introspecting
`license.dat` directly. Routers that gate on Pro-only features can simply::

    if not app.state.features.is_enabled("cascade_intelligence"):
        raise HTTPException(status_code=402, detail="...Pro Edition")

For V3.3 Standard Edition the default set of features is fixed and small;
the registry exists mostly so the same shape can be reused by V5 Pro in a
later backport without a second API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable

from .validator import LicenseClaims

# Features that the Standard Edition is allowed to expose regardless of what
# the license.dat claims. A malformed or permissive license cannot grant Pro
# features on a Std build because this allowlist gates the final answer.
STANDARD_ALLOWLIST = frozenset({
    "core_monitoring",
    "intelligence_kpis",
    "performance_module",
    # "dba_copilot_rule_based",  # REMOVED 2026-05-05 FIND-013-B (V3.3 zero AI policy)
    "capacity_planning_basic",
})


@dataclass(frozen=True)
class FeatureRegistry:
    _flags: Dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_claims(cls, claims: LicenseClaims, *, allowlist: Iterable[str] = STANDARD_ALLOWLIST) -> "FeatureRegistry":
        allowed = frozenset(allowlist)
        resolved = {name: bool(claims.features.get(name, False)) and name in allowed for name in allowed}
        return cls(_flags=resolved)

    @classmethod
    def empty(cls) -> "FeatureRegistry":
        return cls(_flags={name: False for name in STANDARD_ALLOWLIST})

    def is_enabled(self, feature: str) -> bool:
        return bool(self._flags.get(feature, False))

    def as_dict(self) -> Dict[str, bool]:
        return dict(self._flags)
