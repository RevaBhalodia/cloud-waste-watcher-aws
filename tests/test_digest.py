import digest


def item(rid, cost, title="Unattached 10 GB gp3 volume"):
    return {"check": "unattached_volume", "resource_id": rid, "title": title,
            "age_days": 3, "tags": {}, "details": {}, "monthly_usd": cost}


def build(findings, new_ids, **kw):
    return digest.build_digest(findings, new_ids, kw.get("ignored", 0), kw.get("errors", []),
                               "ap-south-1", "2026-10-07", None if new_ids is None else "2026-10-06")


def test_tidy_digest():
    subject, body = build([], None)
    assert subject == "Waste Watcher: all tidy" and "All tidy" in body


def test_new_and_still_there_sections():
    subject, body = build([item("vol-new", 1.8), item("vol-old", 0.9)], {"vol-new"})
    assert "(1 new)" in subject
    before, after = body.split("STILL THERE:")
    assert "vol-new" in before and "vol-old" in after


def test_first_scan_has_no_new_label():
    subject, body = build([item("vol-1", 0.9)], None)
    assert "new" not in subject and "FOUND:" in body


def test_subject_is_ascii_and_short_and_errors_are_listed():
    subject, body = build([item("v", 1.0)] * 3, set(), errors=["old_snapshot: UnauthorizedOperation"])
    assert subject.isascii() and len(subject) <= 100
    assert "UnauthorizedOperation" in body
