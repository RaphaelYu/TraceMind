from __future__ import annotations

import json
import hashlib

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence, cast

from tm.utils.yaml import import_yaml

from tm.artifacts import (
    ArtifactValidationError,
    validate_capability_spec,
    validate_intent_spec,
    validate_policy_spec,
    validate_workflow_policy,
)

yaml = import_yaml()

JSONPointer = str


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_structured(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML required to load YAML patches")
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"{path}: expected mapping document")
    return payload


def _canonical_id_payload(proposal: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "target_artifact_type": proposal.get("target_artifact_type"),
        "target_ref": proposal.get("target_ref"),
        "patch_kind": proposal.get("patch_kind"),
        "changes": proposal.get("changes"),
    }


def _proposal_id_from_payload(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        _canonical_id_payload(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return digest[:12]


def _make_pointer_segments(pointer: JSONPointer) -> list[str]:
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer}")
    parts = pointer.lstrip("/").split("/")
    decoded: list[str] = []
    for part in parts:
        decoded.append(part.replace("~1", "/").replace("~0", "~"))
    return decoded


def _navigate_to_target(root: MutableMapping[str, Any] | list[Any], segment: str) -> tuple[Any, str | int]:
    if isinstance(root, list):
        if segment == "-":
            index = len(root)
        else:
            try:
                index = int(segment)
            except ValueError as exc:
                raise ValueError(f"invalid list index '{segment}'") from exc
        return root, index
    if not isinstance(root, MutableMapping):
        raise ValueError(f"cannot navigate into {type(root)}")
    return root, segment


def _apply_single_change(root: MutableMapping[str, Any], change: Mapping[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(root))
    data = cast(dict[str, Any], payload)
    segments = _make_pointer_segments(str(change["path"]))
    parent: Any = data
    for segment in segments[:-1]:
        if isinstance(parent, list):
            idx = int(segment)
            parent = parent[idx]
        else:
            parent = parent.setdefault(segment, {})
    final_segment = segments[-1]
    op = change.get("op", "replace")
    target_container, key = _navigate_to_target(parent, final_segment)
    if op == "remove":
        if isinstance(target_container, list):
            if isinstance(key, int) and 0 <= key < len(target_container):
                target_container.pop(key)
        else:
            target_container.pop(key, None)
    else:
        value = change.get("value")
        if isinstance(target_container, list):
            if not isinstance(key, int):
                raise ValueError("list index must be integer")
            if key == len(target_container):
                target_container.append(value)
            else:
                target_container[key] = value
        else:
            key_str = str(key)
            target_container[key_str] = value
    return data


def _apply_changes(root: Mapping[str, Any], changes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    updated = dict(root)
    for change in changes:
        updated = _apply_single_change(updated, change)
    return updated


def _bump_version(value: str | None) -> str:
    if not value:
        value = "0.0.0"
    parts = value.split(".")
    nums = []
    for part in parts[:3]:
        try:
            nums.append(int(part))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    nums[2] += 1
    return ".".join(str(num) for num in nums)


VALIDATORS = {
    "policy": validate_policy_spec,
    "intent": validate_intent_spec,
    "workflow": validate_workflow_policy,
    "capability": validate_capability_spec,
}


class PatchStoreError(RuntimeError):
    pass


@dataclass
class PatchEntry:
    proposal_id: str
    status: str
    path: Path
    target_artifact_type: str
    target_ref: str
    created_at: str


class PatchStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or ".tm/patches")
        self.proposals_dir = self.root / "proposals"
        self.applied_dir = self.root / "applied"
        self.index_path = self.root / "index.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        self.applied_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, Any]
        if not self.index_path.exists():
            self._index = {"proposals": {}, "applied": []}
            self._save_index()
        else:
            self._index = self._load_index()

    def _load_index(self) -> dict[str, Any]:
        with self.index_path.open("r", encoding="utf-8") as fh:
            return cast(dict[str, Any], json.load(fh))

    def _save_index(self) -> None:
        with self.index_path.open("w", encoding="utf-8") as fh:
            json.dump(self._index, fh, indent=2, ensure_ascii=False)

    def _write_proposal_file(self, proposal: Mapping[str, Any], path: Path) -> None:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(proposal, fh, indent=2, ensure_ascii=False)

    def _load_proposal_file(self, path: Path) -> dict[str, Any]:
        payload = _load_structured(path)
        if not isinstance(payload, dict):
            raise RuntimeError(f"{path}: expected mapping document")
        return payload

    def _proposal_path(self, proposal_id: str) -> Path:
        return self.proposals_dir / f"{proposal_id}.json"

    def _ensure_proposal(self, proposal_id: str) -> tuple[dict[str, Any], Path]:
        proposals = cast(dict[str, dict[str, Any]], self._index.setdefault("proposals", {}))
        entry = proposals.get(proposal_id)
        if not entry:
            raise PatchStoreError(f"unknown proposal '{proposal_id}'")
        path = self.root / entry["path"]
        if not path.exists():
            raise PatchStoreError(f"proposal file missing at {path}")
        return self._load_proposal_file(path), path

    def _update_index_entry(self, proposal: Mapping[str, Any]) -> None:
        proposals = cast(dict[str, dict[str, Any]], self._index.setdefault("proposals", {}))
        entry = proposals.get(proposal["proposal_id"])
        if not entry:
            raise PatchStoreError(f"proposal '{proposal['proposal_id']}' not registered")
        entry["status"] = proposal["status"]
        entry["target_artifact_type"] = proposal["target_artifact_type"]
        entry["target_ref"] = proposal["target_ref"]
        if proposal.get("applied_at"):
            entry["applied_at"] = proposal["applied_at"]
        self._save_index()

    def _register_proposal(self, proposal: Mapping[str, Any], path: Path) -> None:
        proposals = cast(dict[str, dict[str, Any]], self._index.setdefault("proposals", {}))
        proposals[proposal["proposal_id"]] = {
            "proposal_id": proposal["proposal_id"],
            "status": proposal["status"],
            "path": str(path.relative_to(self.root)),
            "target_artifact_type": proposal["target_artifact_type"],
            "target_ref": proposal["target_ref"],
            "created_at": proposal["created_at"],
        }
        self._save_index()

    def create_draft(
        self,
        *,
        changes: Sequence[Mapping[str, Any]],
        target_artifact_type: str,
        target_ref: str,
        patch_kind: str,
        rationale: str,
        expected_effect: str,
        risk_level: str,
        created_by: str,
        review_notes: Sequence[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> PatchEntry:
        payload: dict[str, Any] = {
            "changes": [dict(change) for change in changes],
            "target_artifact_type": target_artifact_type,
            "target_ref": target_ref,
            "patch_kind": patch_kind,
            "rationale": rationale,
            "expected_effect": expected_effect,
            "risk_level": risk_level,
            "review_notes": list(review_notes or []),
            "metadata": dict(metadata or {}),
        }
        proposal_id = _proposal_id_from_payload(payload)
        payload["proposal_id"] = proposal_id
        payload["created_by"] = created_by
        payload["created_at"] = _timestamp()
        payload["status"] = "DRAFT"
        payload["approvals"] = []
        path = self._proposal_path(proposal_id)
        if path.exists():
            raise PatchStoreError(f"proposal '{proposal_id}' already exists")
        self._write_proposal_file(payload, path)
        self._register_proposal(payload, path)
        return PatchEntry(
            proposal_id=proposal_id,
            status="DRAFT",
            path=path,
            target_artifact_type=target_artifact_type,
            target_ref=target_ref,
            created_at=payload["created_at"],
        )

    def submit_proposal(self, proposal_id: str) -> Path:
        proposal, path = self._ensure_proposal(proposal_id)
        if proposal["status"] != "DRAFT":
            raise PatchStoreError("only DRAFT proposals can be submitted")
        target_path = Path(proposal["target_ref"])
        if not target_path.exists():
            raise PatchStoreError(f"target artifact not found at {target_path}")
        validator = VALIDATORS.get(proposal["target_artifact_type"])
        if validator is None:
            raise PatchStoreError(f"unknown artifact type '{proposal['target_artifact_type']}'")
        try:
            validator(_load_structured(target_path))
        except ArtifactValidationError as exc:
            raise PatchStoreError(f"target artifact invalid: {exc}") from exc
        proposal["status"] = "SUBMITTED"
        proposal["submitted_at"] = _timestamp()
        self._write_proposal_file(proposal, path)
        self._update_index_entry(proposal)
        return path

    def approve_proposal(self, proposal_id: str, *, actor: str, reason: str) -> None:
        proposal, path = self._ensure_proposal(proposal_id)
        if proposal["status"] != "SUBMITTED":
            raise PatchStoreError("only SUBMITTED proposals can be approved")
        approvals = proposal.setdefault("approvals", [])
        approvals.append({"actor": actor, "reason": reason, "timestamp": _timestamp()})
        proposal["status"] = "APPROVED"
        proposal["approved_at"] = _timestamp()
        self._write_proposal_file(proposal, path)
        self._update_index_entry(proposal)

    def apply_proposal(self, proposal_id: str, *, out_dir: Path | None = None) -> Path:
        proposal, path = self._ensure_proposal(proposal_id)
        if proposal["status"] != "APPROVED":
            raise PatchStoreError("only APPROVED proposals can be applied")
        if not proposal.get("approvals"):
            raise PatchStoreError("proposal lacks approvals")
        validator = VALIDATORS.get(proposal["target_artifact_type"])
        if validator is None:
            raise PatchStoreError(f"unknown artifact type '{proposal['target_artifact_type']}'")
        target_path = Path(proposal["target_ref"])
        if not target_path.exists():
            raise PatchStoreError(f"target artifact not found at {target_path}")
        target = _load_structured(target_path)
        updated = _apply_changes(target, proposal["changes"])
        updated["version"] = _bump_version(str(updated.get("version", None)))
        metadata = updated.setdefault("metadata", {})
        metadata["governance"] = metadata.get("governance", {})
        metadata["governance"]["applied_from_proposal_id"] = proposal_id
        validator(updated)
        out_dir = Path(out_dir or self.root.parent / "artifacts")
        out_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"{target_path.stem}.v{updated['version'].replace('.', '_')}.{proposal_id}.json"
        dest_path = out_dir / dest_name
        with dest_path.open("w", encoding="utf-8") as fh:
            json.dump(updated, fh, indent=2, ensure_ascii=False)
        applied_at = _timestamp()
        record = {
            "proposal_id": proposal_id,
            "applied_at": applied_at,
            "target_ref": proposal["target_ref"],
            "artifacts": {
                "source": str(target_path),
                "result": str(dest_path),
            },
        }
        applied = cast(list[dict[str, Any]], self._index.setdefault("applied", []))
        applied.append(record)
        proposal["status"] = "APPLIED"
        proposal["applied_at"] = applied_at
        self._write_proposal_file(proposal, path)
        self._update_index_entry(proposal)
        return dest_path

    def describe(self) -> dict[str, Any]:
        return self._index
