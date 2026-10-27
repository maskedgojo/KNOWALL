"""Module 2 feature readiness. Statuses describe the repository, not a policy.

No permission code is declared here. New codes stay unregistered until
M2-POL-02 is approved and the Module 1 owner adds them to the known set.
"""
from types import MappingProxyType

FEATURES = MappingProxyType({
    "notices": MappingProxyType({
        "status": "in_progress",
        "blockers": (),
    }),
    "discussions": MappingProxyType({
        "status": "in_progress",
        "blockers": ("M2-POL-01",),
    }),
    "suggestions": MappingProxyType({
        "status": "in_progress",
        "blockers": ("M2-POL-01",),
    }),
    "disputes": MappingProxyType({
        "status": "in_progress",
        "blockers": ("M2-POL-10", "M2-POL-11"),
    }),
    "polls": MappingProxyType({
        "status": "in_progress",
        "blockers": ("M2-POL-09",),
    }),
    "proposals": MappingProxyType({
        "status": "in_progress",
        "blockers": ("M2-POL-04", "M2-POL-05", "M2-POL-06", "M2-POL-07", "M2-POL-08"),
    }),
    "transparency": MappingProxyType({
        "status": "in_progress",
        "blockers": ("M2-POL-13",),
    }),
})

UNIMPLEMENTED_API_PREFIXES = (
    "/api/votes",
)


def unimplemented_features() -> tuple[str, ...]:
    return tuple(name for name, item in FEATURES.items() if item["status"] != "complete")
