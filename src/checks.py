"""
Cloud Waste Watcher - checks

Each check is one function: it takes an EC2 client and returns a list of
"findings". Every finding has the same shape (see make_finding), so the
rest of the program never needs to know which check produced it.

All checks are READ-ONLY. Nothing here changes or deletes anything.
"""

import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Your definition of "waste" lives here. Change these numbers to taste.
# ---------------------------------------------------------------------------
STOPPED_INSTANCE_MIN_DAYS = 7   # stopped for less than this = probably just paused
SNAPSHOT_MAX_AGE_DAYS = 90      # snapshots older than this are worth a look


# ---------------------------------------------------------------------------
# Small helpers shared by every check
# ---------------------------------------------------------------------------
def tags_to_dict(tag_list):
    """AWS gives [{"Key": "a", "Value": "b"}]. We want {"a": "b"}."""
    return {tag["Key"]: tag["Value"] for tag in (tag_list or [])}


def age_in_days(timestamp):
    """Whole days since a timezone-aware timestamp, or None if unknown."""
    if timestamp is None:
        return None
    return (datetime.now(timezone.utc) - timestamp).days


def make_finding(check, resource_id, title, age_days=None, tags=None, details=None):
    """The ONE shape every finding must have."""
    return {
        "check": check,
        "resource_id": resource_id,
        "title": title,
        "age_days": age_days,
        "tags": tags or {},
        "details": details or {},
    }


# ---------------------------------------------------------------------------
# Check 1: unattached EBS volumes (your Milestone 1 code, in the new shape)
# ---------------------------------------------------------------------------
def find_unattached_volumes(ec2):
    findings = []
    paginator = ec2.get_paginator("describe_volumes")
    pages = paginator.paginate(Filters=[{"Name": "status", "Values": ["available"]}])

    for page in pages:
        for volume in page["Volumes"]:
            findings.append(
                make_finding(
                    check="unattached_volume",
                    resource_id=volume["VolumeId"],
                    title=f"Unattached {volume['Size']} GB {volume['VolumeType']} volume",
                    age_days=age_in_days(volume["CreateTime"]),
                    tags=tags_to_dict(volume.get("Tags")),
                    details={
                        "size_gb": volume["Size"],
                        "volume_type": volume["VolumeType"],
                    },
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Check 2: Elastic IPs that are not attached to anything
# ---------------------------------------------------------------------------
def find_idle_elastic_ips(ec2):
    findings = []

    # There is no paginator for this call: AWS returns every address at once.
    for address in ec2.describe_addresses()["Addresses"]:
        # An address that is in use has an AssociationId. No ID = idle.
        if "AssociationId" in address:
            continue

        findings.append(
            make_finding(
                check="idle_elastic_ip",
                resource_id=address.get("AllocationId", address["PublicIp"]),
                title=f"Elastic IP {address['PublicIp']} is not attached to anything",
                age_days=None,  # AWS does not record when an address was allocated
                tags=tags_to_dict(address.get("Tags")),
                details={"public_ip": address["PublicIp"]},
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Check 3: instances that have been stopped for a while
# ---------------------------------------------------------------------------
# AWS leaves a note like "User initiated (2026-09-01 10:30:00 GMT)" on a
# stopped instance. It is the only record of WHEN it stopped.
STOP_TIME_PATTERN = re.compile(r"\((\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) GMT\)")


def parse_stop_time(reason):
    match = STOP_TIME_PATTERN.search(reason or "")
    if not match:
        return None
    parsed = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=timezone.utc)


def find_stopped_instances(ec2):
    findings = []
    paginator = ec2.get_paginator("describe_instances")
    pages = paginator.paginate(
        Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
    )

    for page in pages:
        # Instances come grouped inside "Reservations", so there are two loops.
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                stopped_days = age_in_days(
                    parse_stop_time(instance.get("StateTransitionReason"))
                )

                # Recently stopped = probably intentional. Skip it.
                # If we can't tell when it stopped, we report it (safer).
                if stopped_days is not None and stopped_days < STOPPED_INSTANCE_MIN_DAYS:
                    continue

                findings.append(
                    make_finding(
                        check="stopped_instance",
                        resource_id=instance["InstanceId"],
                        title=f"Stopped {instance['InstanceType']} instance",
                        age_days=stopped_days,
                        tags=tags_to_dict(instance.get("Tags")),
                        details={
                            "instance_type": instance["InstanceType"],
                            "attached_volumes": len(
                                instance.get("BlockDeviceMappings", [])
                            ),
                        },
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Check 4: old snapshots
# ---------------------------------------------------------------------------
def find_old_snapshots(ec2):
    findings = []
    paginator = ec2.get_paginator("describe_snapshots")

    # OwnerIds=["self"] is essential: without it AWS lists every PUBLIC
    # snapshot on earth, not just yours.
    for page in paginator.paginate(OwnerIds=["self"]):
        for snapshot in page["Snapshots"]:
            age = age_in_days(snapshot["StartTime"])
            if age < SNAPSHOT_MAX_AGE_DAYS:
                continue

            description = snapshot.get("Description", "")
            findings.append(
                make_finding(
                    check="old_snapshot",
                    resource_id=snapshot["SnapshotId"],
                    title=f"{age}-day-old snapshot of a {snapshot['VolumeSize']} GB volume",
                    age_days=age,
                    tags=tags_to_dict(snapshot.get("Tags")),
                    details={
                        "volume_size_gb": snapshot["VolumeSize"],
                        # Snapshots made for an AMI can't be deleted until the
                        # AMI is deregistered, so flag them.
                        "likely_backs_an_ami": description.startswith(
                            "Created by CreateImage"
                        ),
                    },
                )
            )
    return findings


# ---------------------------------------------------------------------------
# The registry. To add a new check: write the function, add it to this list.
# ---------------------------------------------------------------------------
CHECKS = [
    find_unattached_volumes,
    find_idle_elastic_ips,
    find_stopped_instances,
    find_old_snapshots,
]
