"""
Cloud Waste Watcher - scan.py

Runs every check in checks.CHECKS, estimates what the waste costs, and
prints one report. READ-ONLY: it advises, it never deletes.

Run it with:  python scan.py
"""

from collections import defaultdict

import boto3
from botocore.exceptions import ClientError

import pricing
from checks import CHECKS

REGION = "ap-south-1"  # Mumbai

# Put this tag on anything that is intentionally left alone:
#   waste-watcher:ignore = true
IGNORE_TAG = "waste-watcher:ignore"


def run_all_checks(ec2):
    """Run every check. One broken check must not kill the whole report.

    Returns (findings, errors). No printing here: this is the "detective".
    """
    findings = []
    errors = []

    for check in CHECKS:
        try:
            findings.extend(check(ec2))
        except ClientError as err:
            # e.g. AccessDenied because the role can't read snapshots
            errors.append(f"{check.__name__}: {err.response['Error']['Code']}")

    return findings, errors


def apply_ignore_list(findings):
    """Split findings into (kept, ignored) using the ignore tag."""
    kept, ignored = [], []
    for finding in findings:
        if finding["tags"].get(IGNORE_TAG, "").lower() == "true":
            ignored.append(finding)
        else:
            kept.append(finding)
    return kept, ignored


def print_report(findings, ignored_count, errors):
    """Show the findings in a human-friendly way: this is the "reporter".

    Expects findings that already have a "monthly_usd" field.
    """
    if not findings:
        print("No waste found. Nice and tidy!")
    else:
        estimated = [f for f in findings if f["monthly_usd"] is not None]
        total = sum(f["monthly_usd"] for f in estimated)

        print(f"Found {len(findings)} possible waste item(s).")
        print(f"Estimated waste: {pricing.format_money(total)}")
        not_estimated = len(findings) - len(estimated)
        if not_estimated:
            print(f"({not_estimated} item(s) have no cost estimate yet)")

        # Group findings by which check found them.
        groups = defaultdict(list)
        for finding in findings:
            groups[finding["check"]].append(finding)

        for check_name, items in groups.items():
            print(f"\n== {check_name.replace('_', ' ').title()} ({len(items)}) ==")
            # Most expensive first. Items with no estimate sort last.
            items.sort(key=lambda f: f["monthly_usd"] or 0, reverse=True)
            for item in items:
                age = (
                    f"{item['age_days']} days"
                    if item["age_days"] is not None
                    else "age unknown"
                )
                cost = (
                    pricing.format_money(item["monthly_usd"])
                    if item["monthly_usd"] is not None
                    else "cost not estimated"
                )
                print(f"  {item['resource_id']}  -  {item['title']}")
                print(f"      ~{cost}" if item["monthly_usd"] is not None
                      else f"      {cost}")
                print(f"      age: {age}   tags: {item['tags'] or 'none'}")

        print(f"\nPrices: {pricing.PRICE_NOTE}")

    if ignored_count:
        print(f"\n({ignored_count} item(s) hidden by the '{IGNORE_TAG}' tag)")

    if errors:
        print("\nSome checks could not run:")
        for message in errors:
            print(f"  ! {message}")


def main():
    ec2 = boto3.client("ec2", region_name=REGION)
    findings, errors = run_all_checks(ec2)
    kept, ignored = apply_ignore_list(findings)   # ignored items don't count
    print_report(pricing.with_estimates(kept), len(ignored), errors)


if __name__ == "__main__":
    main()
