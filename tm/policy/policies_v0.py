from typing import Mapping, Sequence

DEFAULT_ALLOWLIST: Sequence[str] = []


def policy_allowlist(meta: Mapping[str, object] | None) -> Sequence[str]:
    if meta is None:
        return []
    policy_meta = meta.get("policy")
    if not isinstance(policy_meta, Mapping):
        return []
    allow = policy_meta.get("allow")
    if not isinstance(allow, Sequence):
        return []
    return [str(item) for item in allow]
