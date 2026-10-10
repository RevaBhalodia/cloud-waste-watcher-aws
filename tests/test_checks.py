from datetime import datetime, timezone

import checks
from conftest import make_volume


def ids(findings):
    return {f["resource_id"] for f in findings}


def test_only_unattached_volumes_are_reported(ec2):
    lonely = make_volume(ec2)
    used = make_volume(ec2)
    instance = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1,
                                 Placement={"AvailabilityZone": "ap-south-1a"})["Instances"][0]["InstanceId"]
    ec2.attach_volume(VolumeId=used, InstanceId=instance, Device="/dev/sdf")
    found = checks.find_unattached_volumes(ec2)
    assert ids(found) == {lonely}
    assert found[0]["details"] == {"size_gb": 10, "volume_type": "gp3"}


def test_idle_elastic_ip_but_not_associated_one(ec2):
    idle = ec2.allocate_address(Domain="vpc")["AllocationId"]
    used = ec2.allocate_address(Domain="vpc")["AllocationId"]
    instance = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]
    ec2.associate_address(InstanceId=instance, AllocationId=used)
    assert ids(checks.find_idle_elastic_ips(ec2)) == {idle}


def test_stopped_instance_with_unknown_stop_time_is_still_reported(ec2):
    instance = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]
    ec2.stop_instances(InstanceIds=[instance])
    found = checks.find_stopped_instances(ec2)
    assert instance in ids(found)  # we can't tell when it stopped, so we err on the side of reporting


def test_parse_stop_time():
    parsed = checks.parse_stop_time("User initiated (2026-09-01 10:30:12 GMT)")
    assert parsed == datetime(2026, 9, 1, 10, 30, 12, tzinfo=timezone.utc)
    assert checks.parse_stop_time(None) is None
    assert checks.parse_stop_time("Client.UserInitiatedShutdown") is None


def test_snapshot_threshold(ec2, monkeypatch):
    volume = make_volume(ec2)
    snapshot = ec2.create_snapshot(VolumeId=volume)["SnapshotId"]
    assert snapshot not in ids(checks.find_old_snapshots(ec2))      # brand new: not old
    monkeypatch.setattr(checks, "SNAPSHOT_MAX_AGE_DAYS", 0)
    assert snapshot in ids(checks.find_old_snapshots(ec2))          # threshold lowered: now it counts
