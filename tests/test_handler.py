import json

import boto3
import pytest

import lambda_function
import pricing
import scan
import storage
from conftest import REGION, make_volume


@pytest.fixture
def inbox(aws, table, monkeypatch):
    """An SNS topic wired to an SQS queue so a test can read the 'email'."""
    sns, sqs = boto3.client("sns", region_name=REGION), boto3.client("sqs", region_name=REGION)
    topic = sns.create_topic(Name="digest")["TopicArn"]
    url = sqs.create_queue(QueueName="inbox")["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    sns.subscribe(TopicArn=topic, Protocol="sqs", Endpoint=arn)
    monkeypatch.setenv("TABLE_NAME", "findings")
    monkeypatch.setenv("TOPIC_ARN", topic)

    def read():
        messages = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10).get("Messages", [])
        return [json.loads(m["Body"]) for m in messages]
    return read


def test_first_scan_of_a_tidy_account(inbox):
    result = lambda_function.lambda_handler({}, None)
    assert result["items_found"] == 0 and result["items_new"] is None
    assert result["saved_to_dynamodb"] and result["digest_sent"]
    assert inbox()[0]["Subject"] == "Waste Watcher: all tidy"


def test_new_versus_still_there(ec2, table, inbox):
    old = make_volume(ec2)
    earlier, _ = scan.run_all_checks(ec2)
    storage.save_scan(table, "2026-10-05", REGION, pricing.with_estimates(earlier), 0.9, 0)
    new = make_volume(ec2, size=20)

    result = lambda_function.lambda_handler({}, None)
    assert result["items_found"] == 2 and result["items_new"] == 1 and result["errors"] == []
    body = inbox()[0]["Message"]
    before, after = body.split("STILL THERE:")
    assert new in before and old in after


def test_running_twice_on_the_same_day_creates_no_duplicates(ec2, table, inbox):
    make_volume(ec2)
    lambda_function.lambda_handler({}, None)
    lambda_function.lambda_handler({}, None)
    scan_date = lambda_function.lambda_handler({}, None)["scan_date"]
    items = table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq(f"SCAN#{scan_date}"))["Items"]
    assert len(items) == 1


def test_a_broken_table_does_not_stop_the_email(ec2, inbox, monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "does-not-exist")
    result = lambda_function.lambda_handler({}, None)
    assert result["saved_to_dynamodb"] is False and result["digest_sent"] is True
    assert result["errors"][0].startswith("save_to_dynamodb:")


def test_works_with_no_settings_at_all(ec2):
    result = lambda_function.lambda_handler({}, None)
    assert result["saved_to_dynamodb"] is False and result["digest_sent"] is False
