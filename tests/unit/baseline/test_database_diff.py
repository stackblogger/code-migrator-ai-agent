from migrator.baseline.database import _identifier, _literal, diff_snapshots


def test_added_removed_and_changed_rows():
    before = {"users": [{"id": 1, "email": "a"}, {"id": 2, "email": "b"}], "orders": []}
    after = {
        "users": [{"id": 1, "email": "a"}, {"id": 2, "email": "B"}, {"id": 10, "email": "c"}],
        "orders": [],
    }
    changes = diff_snapshots(before, after)
    assert list(changes) == ["users"]  # unchanged tables are left out
    assert changes["users"].added == [{"id": 2, "email": "B"}, {"id": 10, "email": "c"}]
    assert changes["users"].removed == [{"id": 2, "email": "b"}]


def test_new_table_and_duplicate_rows():
    changes = diff_snapshots({}, {"logs": [{"msg": "x"}, {"msg": "x"}]})
    assert changes["logs"].added == [{"msg": "x"}, {"msg": "x"}]


def test_sql_quoting():
    assert _identifier('we"ird') == '"we""ird"'
    assert _literal("it's") == "'it''s'"
