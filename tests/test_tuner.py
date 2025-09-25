from tm.ai.observer import Observation
from tm.ai.tuner import propose


def test_tuner_proposes_when_pending_high():
    observation = Observation(counters={"flows_deferred_pending()": 10}, gauges={})
    policy = {"flow": {"delay": 2}}

    result = propose(observation, policy)

    assert result is not None
    assert any(change.path == "flow.delay" for change in result.changes)
