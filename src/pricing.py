"""
Cloud Waste Watcher - pricing

Turns findings into rough monthly cost estimates.

IMPORTANT - READ THIS FIRST
The prices below are US East (N. Virginia) list prices. They are PLACEHOLDERS
for your region (Mumbai, ap-south-1), which usually costs a bit more.
TODO 1: look up the Mumbai prices and replace the numbers, then update
        PRICE_NOTE so the report stops saying "placeholder".

Where to look: the Amazon EBS pricing page, the Amazon VPC pricing page
(Public IPv4 Address tab), and the AWS Pricing Calculator. Pick the
Asia Pacific (Mumbai) region on each page.
"""

PRICE_NOTE = (
    "gp3 is the Mumbai price from the AWS Price List (published 2026-09-25); "
    "other prices are US East placeholders. Treat totals as a rough guide."
)

# The exchange rate moves daily. It was about 96.5 in July 2026.
# TODO 2: update this when you run the tool.
USD_TO_INR = 96.5

HOURS_PER_MONTH = 730  # AWS bills in hours; 730 is the usual "average month"

# Dollars per GB per month, by EBS volume type.
EBS_USD_PER_GB_MONTH = {
    "gp3": 0.0912,  # Mumbai, from the AWS Price List
    "gp2": 0.10,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
}

SNAPSHOT_USD_PER_GB_MONTH = 0.05

# Since Feb 2024 AWS charges for every public IPv4 address, per hour.
PUBLIC_IPV4_USD_PER_HOUR = 0.005


# ---------------------------------------------------------------------------
# One small estimator per check. Each takes the finding's "details" dict and
# returns dollars per month, or None when we honestly can't tell.
# ---------------------------------------------------------------------------
def estimate_unattached_volume(details):
    rate = EBS_USD_PER_GB_MONTH.get(details["volume_type"])
    if rate is None:
        return None  # unknown volume type: better "no estimate" than a wrong one
    return details["size_gb"] * rate


def estimate_idle_elastic_ip(details):
    return PUBLIC_IPV4_USD_PER_HOUR * HOURS_PER_MONTH


def estimate_old_snapshot(details):
    # Snapshots are incremental: AWS bills only for the data that changed, so
    # the full volume size is an UPPER BOUND on the real cost.
    return details["volume_size_gb"] * SNAPSHOT_USD_PER_GB_MONTH


def estimate_stopped_instance(details):
    # A stopped instance costs nothing for compute. Its cost is its attached
    # disks and any Elastic IP, which we don't look up yet. Say "unknown".
    return None


# The registry again: same pattern as CHECKS in checks.py.
ESTIMATORS = {
    "unattached_volume": estimate_unattached_volume,
    "idle_elastic_ip": estimate_idle_elastic_ip,
    "old_snapshot": estimate_old_snapshot,
    "stopped_instance": estimate_stopped_instance,
}


def estimate_monthly_usd(finding):
    estimator = ESTIMATORS.get(finding["check"])
    if estimator is None:
        return None
    return estimator(finding["details"])


def with_estimates(findings):
    """Return COPIES of the findings with a "monthly_usd" field added.

    We build new dicts instead of editing the originals, so the checks'
    output stays untouched and easy to reason about.
    """
    return [{**f, "monthly_usd": estimate_monthly_usd(f)} for f in findings]


def format_money(usd):
    return f"${usd:,.2f}/month (about INR {usd * USD_TO_INR:,.0f})"
