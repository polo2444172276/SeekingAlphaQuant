import json

from seekingalpha_quant.data import supabase_db as db


def test_ascii_header_roundtrip():
    for s in ["plain", "测试 note", 'quote " and \\ backslash']:
        enc = db._ascii(s)
        enc.encode("ascii")
        assert json.loads(f'"{enc}"') == s


def test_change_note_restores_header():
    assert "x-change-note" not in db._session.headers
    with db.change_note("a"):
        with db.change_note("b"):
            assert db._session.headers["x-change-note"] == "b"
        assert db._session.headers["x-change-note"] == "a"
    assert "x-change-note" not in db._session.headers
