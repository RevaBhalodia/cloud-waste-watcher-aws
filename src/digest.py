"""
Cloud Waste Watcher - digest

build_digest() turns findings into a plain-text email. It is a pure function
(no AWS calls), so it is easy to test and easy to reword.
send_digest() hands the text to Amazon SNS, which emails the subscribers.
"""

import pricing


def _sorted_by_cost(findings):
    return sorted(findings, key=lambda f: f["monthly_usd"] or 0, reverse=True)


def _item_lines(finding):
    age = (
        f"{finding['age_days']} days old"
        if finding["age_days"] is not None
        else "age unknown"
    )
    cost = (
        pricing.format_money(finding["monthly_usd"])
        if finding["monthly_usd"] is not None
        else "cost not estimated"
    )
    return [
        f"  - {finding['resource_id']}: {finding['title']}",
        f"      {cost}, {age}",
    ]


def build_digest(findings, new_ids, ignored_count, errors, region, scan_date, previous_date):
    """Return (subject, body).

    new_ids is the set of resource ids that were NOT in the previous scan,
    or None when there is no previous scan to compare with.
    """
    total = sum(f["monthly_usd"] for f in findings if f["monthly_usd"] is not None)
    new_findings = (
        [f for f in findings if f["resource_id"] in new_ids] if new_ids is not None else []
    )
    old_findings = (
        [f for f in findings if f["resource_id"] not in new_ids]
        if new_ids is not None
        else list(findings)
    )

    # SNS subjects must be plain ASCII on one line, 100 characters at most.
    if findings:
        subject = f"Waste Watcher: {len(findings)} item(s), about ${total:,.2f}/month"
        if new_findings:
            subject += f" ({len(new_findings)} new)"
    else:
        subject = "Waste Watcher: all tidy"

    lines = [
        "Cloud Waste Watcher - daily digest",
        f"Scan date: {scan_date}    Region: {region}",
        "",
    ]

    if not findings:
        lines.append("All tidy: no waste found today.")
    else:
        lines.append(f"Estimated waste: {pricing.format_money(total)}")
        summary = f"{len(findings)} item(s) found"
        if new_ids is not None:
            summary += f", {len(new_findings)} new since {previous_date}"
        lines.append(summary + ".")

        if new_findings:
            lines += ["", f"NEW since {previous_date}:"]
            for finding in _sorted_by_cost(new_findings):
                lines += _item_lines(finding)

        if old_findings:
            heading = "STILL THERE:" if new_ids is not None else "FOUND:"
            lines += ["", heading]
            for finding in _sorted_by_cost(old_findings):
                lines += _item_lines(finding)

    if ignored_count:
        lines += ["", f"({ignored_count} item(s) hidden by the waste-watcher:ignore tag)"]

    if errors:
        lines += ["", "Some checks could not run:"]
        lines += [f"  ! {message}" for message in errors]

    lines += [
        "",
        "To leave something alone on purpose, tag it:  waste-watcher:ignore = true",
        f"Prices: {pricing.PRICE_NOTE}",
    ]
    return subject, "\n".join(lines)


def send_digest(sns_client, topic_arn, subject, body):
    sns_client.publish(TopicArn=topic_arn, Subject=subject[:100], Message=body)
