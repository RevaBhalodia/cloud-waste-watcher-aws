import json

import api_function
import storage


def call(token=None):
    headers = {"authorization": f"Bearer {token}"} if token else {}
    return api_function.lambda_handler({"headers": headers}, None)


def finding(rid, cost):
    return {"check": "unattached_volume", "resource_id": rid, "title": "x", "age_days": 3,
            "tags": {}, "details": {}, "monthly_usd": cost}


def test_rejects_missing_and_wrong_tokens(table, monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "findings")
    monkeypatch.setenv("DASHBOARD_TOKEN", "s3cret")
    assert call()["statusCode"] == 401
    assert call("wrong")["statusCode"] == 401


def test_returns_history_oldest_first_and_latest_findings(table, monkeypatch):
    monkeypatch.setenv("TABLE_NAME", "findings")
    monkeypatch.setenv("DASHBOARD_TOKEN", "s3cret")
    assert json.loads(call("s3cret")["body"])["history"] == []
    storage.save_scan(table, "2026-10-06", "r", [finding("vol-1", 0.9)], 0.9, 0)
    storage.save_scan(table, "2026-10-07", "r", [finding("vol-1", 0.9), finding("vol-2", 1.8)], 2.7, 0)
    body = json.loads(call("s3cret")["body"])
    assert body["scan_date"] == "2026-10-07"
    assert [h["date"] for h in body["history"]] == ["2026-10-06", "2026-10-07"]
    assert len(body["findings"]) == 2
