from fastapi import APIRouter
from tm.ai.policy_store import PolicyStore
from tm.ai.controller import AIController

router = APIRouter(prefix="/ai")
store = PolicyStore(path="data/policies.json")
ctl = AIController(store, audit_dir="data/trace")


@router.get("/policies")
def get_policies():
    return ctl.list_policies()
