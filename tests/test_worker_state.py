from repomind.pipeline.queue import Worker
from repomind.state import StateStore


def make_state(tmp_path):
    return StateStore(tmp_path / "state.sqlite3")


def test_worker_succeeds_without_retry(tmp_path):
    state = make_state(tmp_path)
    seen = []
    w = Worker(lambda job: seen.append(job), state, max_retries=3, sleeper=lambda _: None)
    assert w.process({"x": 1}) is True
    assert seen == [{"x": 1}]
    assert state.list_dead_letters() == []


def test_worker_retries_then_succeeds(tmp_path):
    state = make_state(tmp_path)
    attempts = {"n": 0}

    def flaky(job):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("transient")

    w = Worker(flaky, state, max_retries=5, sleeper=lambda _: None)
    assert w.process({"id": "a"}) is True
    assert attempts["n"] == 3
    assert state.list_dead_letters() == []


def test_worker_dead_letters_after_exhausting_retries(tmp_path):
    state = make_state(tmp_path)

    def always_fail(job):
        raise ValueError("boom")

    w = Worker(always_fail, state, max_retries=3, sleeper=lambda _: None)
    assert w.process({"id": "bad"}) is False
    dls = state.list_dead_letters()
    assert len(dls) == 1
    assert dls[0]["job"] == {"id": "bad"}
    assert "boom" in dls[0]["error"]


def test_replay_dead_letters(tmp_path):
    state = make_state(tmp_path)
    state.add_dead_letter({"id": "x"}, "old error")
    w = Worker(lambda job: None, state, sleeper=lambda _: None)
    ok, fail = w.replay_dead_letters()
    assert (ok, fail) == (1, 0)
    assert state.list_dead_letters() == []


def test_state_idempotency_log(tmp_path):
    state = make_state(tmp_path)
    assert not state.is_processed("guid-1")
    state.mark_processed("guid-1")
    assert state.is_processed("guid-1")
    state.mark_processed("guid-1")  # idempotent
    assert state.is_processed("guid-1")


def test_state_cursor(tmp_path):
    state = make_state(tmp_path)
    assert state.get_cursor("git") is None
    state.set_cursor("git", "abc123")
    assert state.get_cursor("git") == "abc123"
    state.set_cursor("git", "def456")
    assert state.get_cursor("git") == "def456"
