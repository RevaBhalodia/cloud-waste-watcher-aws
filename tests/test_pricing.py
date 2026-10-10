import pricing


def finding(check, **details):
    return {"check": check, "details": details}


def test_volume_cost_uses_mumbai_gp3_price():
    assert pricing.estimate_monthly_usd(finding("unattached_volume", size_gb=10, volume_type="gp3")) == 10 * 0.0912


def test_unknown_volume_type_gives_no_estimate():
    assert pricing.estimate_monthly_usd(finding("unattached_volume", size_gb=5, volume_type="weird")) is None


def test_elastic_ip_cost():
    assert round(pricing.estimate_monthly_usd(finding("idle_elastic_ip")), 2) == 3.65


def test_snapshot_cost_is_upper_bound_and_stopped_instance_is_unknown():
    assert pricing.estimate_monthly_usd(finding("old_snapshot", volume_size_gb=100)) == 5.0
    assert pricing.estimate_monthly_usd(finding("stopped_instance")) is None


def test_with_estimates_does_not_change_the_originals():
    original = [{"check": "idle_elastic_ip", "details": {}}]
    result = pricing.with_estimates(original)
    assert "monthly_usd" not in original[0] and "monthly_usd" in result[0]
