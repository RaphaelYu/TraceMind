from tm.flow.policies import parse_policies_from_cfg, StepPolicies, RetryPolicy, TimeoutPolicy


def test_parse_policies_defaults():
    policies = parse_policies_from_cfg({})

    assert policies == StepPolicies()


def test_parse_policies_prefers_timeout_dict_and_casts_retry_values():
    cfg = {
        "retry": {"max_attempts": "3", "backoff_ms": "250"},
        "timeout_ms": 999,
        "timeout": {"timeout_ms": "1500"},
    }

    policies = parse_policies_from_cfg(cfg)

    assert policies.retry == RetryPolicy(max_attempts=3, backoff_ms=250)
    assert policies.timeout == TimeoutPolicy(timeout_ms=1500)


def test_parse_policies_normalizes_empty_timeout():
    cfg = {"timeout": {"timeout_ms": ""}}

    policies = parse_policies_from_cfg(cfg)

    assert policies.timeout == TimeoutPolicy(timeout_ms=None)
