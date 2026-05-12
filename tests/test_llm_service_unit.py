from types import SimpleNamespace

from qa_bugs.llm.service import LLMService


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]

    def model_dump(self):
        return {"choices": [{"message": {"content": self.choices[0].message.content}}]}


class _CreateRecorder:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


def _make_client(create_callable):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_callable)
        )
    )


def _make_service(monkeypatch, create_callable, **overrides):
    config = {
        "enabled": True,
        "provider": "azure",
        "deployment": "gpt-5.4",
        "temperature": 0.2,
        "max_tokens": 700,
    }
    config.update(overrides)
    client = _make_client(create_callable)
    monkeypatch.setattr("qa_bugs.llm.service.AzureOpenAI", lambda **_: client)
    return LLMService(config)


def test_chat_gpt5_omits_temperature_and_uses_safe_token_floor(monkeypatch):
    recorder = _CreateRecorder([_FakeResponse("ok")])
    service = _make_service(monkeypatch, recorder, deployment="gpt-5.4")

    ok, txt, err = service._chat(
        model="gpt-5.4",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=700,
        metric_id="m1",
    )

    assert ok is True
    assert txt == "ok"
    assert err is None
    assert len(recorder.calls) == 1
    sent = recorder.calls[0]
    assert "temperature" not in sent
    assert sent["max_completion_tokens"] == 1200


def test_chat_non_gpt5_sends_temperature_and_requested_tokens(monkeypatch):
    recorder = _CreateRecorder([_FakeResponse("ok")])
    service = _make_service(monkeypatch, recorder, deployment="gpt-4o")

    ok, txt, err = service._chat(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.3,
        max_tokens=333,
        metric_id="m2",
    )

    assert ok is True
    assert txt == "ok"
    assert err is None
    sent = recorder.calls[0]
    assert sent["temperature"] == 0.3
    assert sent["max_completion_tokens"] == 333


def test_chat_gpt5_uses_configured_token_override(monkeypatch):
    recorder = _CreateRecorder([_FakeResponse("ok")])
    service = _make_service(monkeypatch, recorder, max_tokens_gpt5=1600)

    ok, txt, err = service._chat(
        model="gpt-5.4",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=700,
        metric_id="m3",
    )

    assert ok is True
    assert txt == "ok"
    assert err is None
    sent = recorder.calls[0]
    assert sent["max_completion_tokens"] == 1600


def test_chat_retries_without_temperature_when_provider_rejects_it(monkeypatch):
    recorder = _CreateRecorder([
        Exception("Unsupported value: 'temperature'"),
        _FakeResponse("retry-ok"),
    ])
    service = _make_service(monkeypatch, recorder, deployment="gpt-4o")

    ok, txt, err = service._chat(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=200,
        metric_id="m4",
    )

    assert ok is True
    assert txt == "retry-ok"
    assert err is None
    assert len(recorder.calls) == 2
    assert "temperature" in recorder.calls[0]
    assert "temperature" not in recorder.calls[1]


def test_model_fallback_respects_fail_fast_when_retries_disabled(monkeypatch):
    recorder = _CreateRecorder([_FakeResponse("unused")])
    service = _make_service(monkeypatch, recorder, enable_retries=False)

    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        return False, None, "EmptyResponse: model returned no text content"

    monkeypatch.setattr(service, "_chat", fake_chat)

    ok, txt, err = service._chat_with_model_fallback(
        model="gpt-5.4",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=700,
        metric_id="m5",
    )

    assert ok is False
    assert txt is None
    assert "EmptyResponse" in err
    assert len(calls) == 1


def test_model_fallback_retries_with_larger_budget_when_enabled(monkeypatch):
    recorder = _CreateRecorder([_FakeResponse("unused")])
    service = _make_service(monkeypatch, recorder, enable_retries=True)

    calls = []

    def fake_chat(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return False, None, "EmptyResponse: model returned no text content"
        return True, "ok-after-retry", None

    monkeypatch.setattr(service, "_chat", fake_chat)

    ok, txt, err = service._chat_with_model_fallback(
        model="gpt-5.4",
        messages=[{"role": "user", "content": "hello"}],
        temperature=0.2,
        max_tokens=700,
        metric_id="m6",
    )

    assert ok is True
    assert txt == "ok-after-retry"
    assert err is None
    assert len(calls) == 2
    assert calls[0]["max_tokens"] == 700
    assert calls[1]["max_tokens"] == 2100
