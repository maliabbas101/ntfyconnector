from app.ntfy_cursor import CursorStore

def test_cursor_survives_restart(tmp_path):
    path = str(tmp_path / "bridge" / "cursor.sqlite")
    first = CursorStore(path, "alerts")
    assert first.get() is None
    first.acknowledge("event-1")
    first.close()
    second = CursorStore(path, "alerts")
    assert second.get() == "event-1"
    second.acknowledge("event-2")
    assert second.get() == "event-2"
    second.close()

def test_cursor_is_topic_scoped(tmp_path):
    path = str(tmp_path / "cursor.sqlite")
    a = CursorStore(path, "a")
    a.acknowledge("a1")
    a.close()
    b = CursorStore(path, "b")
    assert b.get() is None
    b.close()
