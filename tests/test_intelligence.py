from murn.intelligence import classify_request


def test_direct_coding_request_uses_low_temperature_profile():
    profile = classify_request("esse traceback do FastAPI ta dando TypeError")
    assert profile.name == "coding"
    assert profile.temperature <= 0.2


def test_language_request_uses_language_profile():
    profile = classify_request("corrija esse texto mas mantenha meu jeito de falar")
    assert profile.name == "language"
    assert profile.temperature > 0.4


def test_factual_request_is_conservative():
    profile = classify_request("quem criou o murn.?")
    assert profile.name == "factual"
    assert profile.temperature < 0.3


def test_unrelated_small_talk_after_code_is_not_stuck_in_coding():
    history = [
        {"role": "user", "content": "me ajuda com esse codigo python"},
        {"role": "assistant", "content": "achei o bug na funcao"},
    ]
    assert classify_request("valeu man", history).name == "general"


def test_short_coding_followup_keeps_coding_profile():
    history = [
        {"role": "user", "content": "me ajuda com esse codigo python"},
        {"role": "assistant", "content": "o problema esta nessa funcao"},
    ]
    assert classify_request("melhora isso", history).name == "coding"
