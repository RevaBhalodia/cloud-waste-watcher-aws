from botocore.exceptions import ClientError

import scan
from conftest import make_volume


def test_ignore_tag_hides_items(ec2):
    make_volume(ec2)
    quiet = make_volume(ec2, tags={"waste-watcher:ignore": "true"})
    findings, errors = scan.run_all_checks(ec2)
    kept, ignored = scan.apply_ignore_list(findings)
    assert errors == []
    assert [f["resource_id"] for f in ignored] == [quiet]
    assert quiet not in {f["resource_id"] for f in kept}


def test_one_broken_check_does_not_kill_the_report(ec2, monkeypatch):
    def broken(_ec2):
        raise ClientError({"Error": {"Code": "UnauthorizedOperation", "Message": "no"}}, "DescribeX")
    monkeypatch.setattr(scan, "CHECKS", [broken] + scan.CHECKS)
    make_volume(ec2)
    findings, errors = scan.run_all_checks(ec2)
    assert errors == ["broken: UnauthorizedOperation"]
    assert any(f["check"] == "unattached_volume" for f in findings)
