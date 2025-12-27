from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:
    yaml = None

from tm.patch.store import PatchStore, PatchStoreError


def _load_structured(path: Path) -> Mapping[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        if yaml is None:
            raise RuntimeError("PyYAML required; install via `pip install trace-mind[yaml]`")
        payload = yaml.safe_load(text)
    else:
        payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: expected mapping document")
    return payload


def _parse_kv_pairs(values: Sequence[str] | None) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for raw in values or []:
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        pairs[key.strip()] = value.strip()
    return pairs


def _resolve_proposal_reference(arg: str, store: PatchStore) -> str:
    path = Path(arg)
    if path.exists():
        payload = _load_structured(path)
        proposal_id = payload.get("proposal_id")
        if not isinstance(proposal_id, str):
            raise ValueError(f"{path}: missing proposal_id")
        return proposal_id
    return arg


def register_patch_commands(subparsers: argparse._SubParsersAction) -> None:
    patch_parser = subparsers.add_parser("patch", help="governed patch lifecycle")
    patch_sub = patch_parser.add_subparsers(dest="patch_cmd")
    patch_sub.required = True

    propose_parser = patch_sub.add_parser("propose", help="create a draft PatchProposal")
    propose_parser.add_argument("--from", dest="source", required=True, help="patch file containing changes")
    propose_parser.add_argument("--created-by", required=True, help="author of the proposal")
    propose_parser.add_argument(
        "--target",
        choices=["policy", "intent", "workflow", "capability"],
        required=True,
        help="artifact type the proposal targets",
    )
    propose_parser.add_argument(
        "--target-ref",
        required=True,
        help="path or ID of the artifact under change",
    )
    propose_parser.add_argument("--kind", required=True, help="patch kind label (tighten_guard, add_rule, etc.)")
    propose_parser.add_argument("--rationale", required=True, help="why this change is needed")
    propose_parser.add_argument("--expected-effect", required=True, help="high-level effect of the patch")
    propose_parser.add_argument(
        "--risk-level",
        choices=["low", "medium", "high"],
        required=True,
        help="risk classification for the patch",
    )
    propose_parser.add_argument("--review-note", action="append", help="additional note for reviewers")
    propose_parser.add_argument(
        "--meta",
        action="append",
        help="additional metadata in key=value form",
    )
    propose_parser.add_argument(
        "--store-root",
        help="custom patch store root (default: .tm/patches)",
    )
    propose_parser.set_defaults(func=_cmd_patch_propose)

    submit_parser = patch_sub.add_parser("submit", help="submit a proposal for review")
    submit_parser.add_argument("proposal", help="proposal id or file path")
    submit_parser.add_argument(
        "--store-root",
        help="custom patch store root (default: .tm/patches)",
    )
    submit_parser.set_defaults(func=_cmd_patch_submit)

    approve_parser = patch_sub.add_parser("approve", help="approve a submitted proposal")
    approve_parser.add_argument("proposal", help="proposal id or file path")
    approve_parser.add_argument("--actor", required=True, help="approver identity")
    approve_parser.add_argument("--reason", required=True, help="reason for approval")
    approve_parser.add_argument(
        "--store-root",
        help="custom patch store root (default: .tm/patches)",
    )
    approve_parser.set_defaults(func=_cmd_patch_approve)

    apply_parser = patch_sub.add_parser("apply", help="apply an approved proposal")
    apply_parser.add_argument("proposal", help="proposal id or file path")
    apply_parser.add_argument(
        "--out-dir",
        help="directory to emit the new artifact (default: .tm/artifacts)",
    )
    apply_parser.add_argument(
        "--store-root",
        help="custom patch store root (default: .tm/patches)",
    )
    apply_parser.set_defaults(func=_cmd_patch_apply)


def _cmd_patch_propose(args: argparse.Namespace) -> int:
    store = PatchStore(root=Path(args.store_root) if args.store_root else None)
    try:
        payload = _load_structured(Path(args.source))
    except Exception as exc:
        print(f"patch propose: failed to load patch: {exc}", file=sys.stderr)
        raise SystemExit(1)
    changes = payload.get("changes")
    if not isinstance(changes, Sequence) or isinstance(changes, (str, bytes, bytearray)):
        print("patch propose: source file must contain a 'changes' array", file=sys.stderr)
        raise SystemExit(1)

    metadata = _parse_kv_pairs(args.meta)
    try:
        entry = store.create_draft(
            changes=[dict(change) for change in changes],
            target_artifact_type=args.target,
            target_ref=args.target_ref,
            patch_kind=args.kind,
            rationale=args.rationale,
            expected_effect=args.expected_effect,
            risk_level=args.risk_level,
            created_by=args.created_by,
            review_notes=args.review_note,
            metadata=metadata,
        )
    except PatchStoreError as exc:
        print(f"patch propose: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps({"proposal_id": entry.proposal_id, "path": str(entry.path)}, indent=2))
    return 0


def _cmd_patch_submit(args: argparse.Namespace) -> int:
    store = PatchStore(root=Path(args.store_root) if args.store_root else None)
    try:
        pid = _resolve_proposal_reference(args.proposal, store)
        store.submit_proposal(pid)
    except (PatchStoreError, Exception) as exc:
        print(f"patch submit: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"proposal {pid} submitted")
    return 0


def _cmd_patch_approve(args: argparse.Namespace) -> int:
    store = PatchStore(root=Path(args.store_root) if args.store_root else None)
    try:
        pid = _resolve_proposal_reference(args.proposal, store)
        store.approve_proposal(pid, actor=args.actor, reason=args.reason)
    except (PatchStoreError, Exception) as exc:
        print(f"patch approve: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"proposal {pid} approved")
    return 0


def _cmd_patch_apply(args: argparse.Namespace) -> int:
    store = PatchStore(root=Path(args.store_root) if args.store_root else None)
    try:
        pid = _resolve_proposal_reference(args.proposal, store)
        path = store.apply_proposal(pid, out_dir=Path(args.out_dir) if args.out_dir else None)
    except (PatchStoreError, Exception) as exc:
        print(f"patch apply: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"proposal {pid} applied -> {path}")
    return 0
