from vharness.assessment import AssessmentStore
from vharness.tools import ToolAction, ToolResult


def test_session_action_and_result_are_durable(tmp_path):
    path = tmp_path / "assessment.sqlite3"
    store = AssessmentStore(path)
    session = store.create_session(["10.0.0.5"])
    action = ToolAction("http_request", "http://10.0.0.5/")
    store.record_action(session.session_id, action)
    assert store.action_seen(session.session_id, action)
    store.record_result(ToolResult(action.action_id, "ok", {"status": 200}))
    store.close()

    reopened = AssessmentStore(path)
    assert reopened.session(session.session_id).targets == ["10.0.0.5"]
    assert reopened.action_seen(session.session_id, action)
    reopened.close()


def test_action_fingerprint_is_stable():
    a = ToolAction("probe", "target", {"ports": [80, 443]})
    b = ToolAction("probe", "target", {"ports": [80, 443]})
    assert a.fingerprint == b.fingerprint
