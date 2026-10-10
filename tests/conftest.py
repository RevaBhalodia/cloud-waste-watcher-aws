import boto3
import pytest
from moto import mock_aws

REGION = "ap-south-1"


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Fake credentials, so a test can NEVER touch a real AWS account."""
    for key, value in {
        "AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": REGION, "AWS_REGION": REGION,
    }.items():
        monkeypatch.setenv(key, value)
    for key in ("TABLE_NAME", "TOPIC_ARN", "SCAN_REGION", "DASHBOARD_TOKEN"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def aws():
    with mock_aws():  # a pretend AWS that lives only inside the test
        yield


@pytest.fixture
def ec2(aws):
    return boto3.client("ec2", region_name=REGION)


@pytest.fixture
def table(aws):
    return boto3.resource("dynamodb", region_name=REGION).create_table(
        TableName="findings",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def make_volume(ec2, size=10, vtype="gp3", tags=None):
    kwargs = {"AvailabilityZone": "ap-south-1a", "Size": size, "VolumeType": vtype}
    if tags:
        kwargs["TagSpecifications"] = [{"ResourceType": "volume",
                                        "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}]
    return ec2.create_volume(**kwargs)["VolumeId"]
