"""Pruebas unitarias de ``app.security``: claves por cliente y límite de peticiones."""

import hmac
import threading

import pytest

from conftest import ManualClock

from app.security import RateLimiter, parse_api_keys

TEACHER_KEY = "teacher-key-0123456789"
OFFICE_KEY = "office-key-9876543210"


def test_api_keys_are_parsed_by_client_trimming_spaces_and_splitting_on_first_colon():
    single = parse_api_keys("teacher:" + TEACHER_KEY)
    assert single.identify(TEACHER_KEY) == "teacher"

    several = parse_api_keys(f" teacher : {TEACHER_KEY} , office:{OFFICE_KEY} ")
    assert several.identify(TEACHER_KEY) == "teacher"
    assert several.identify(OFFICE_KEY) == "office"

    with_colon = parse_api_keys("robot:abc:def-0123456789")
    assert with_colon.identify("abc:def-0123456789") == "robot"
    assert with_colon.identify("def-0123456789") is None


def test_malformed_api_keys_report_the_entry_and_its_length_but_never_the_value():
    malformed = {
        "teacher-without-colon": "entry 1",
        f"teacher:{TEACHER_KEY},": "entry 2",
        f":{TEACHER_KEY}": "entry 1",
        "teacher:   ": "entry 1",
        f"teacher:{TEACHER_KEY},teacher:{OFFICE_KEY}": "entry 2",
    }
    for raw, entry in malformed.items():
        with pytest.raises(ValueError) as error:
            parse_api_keys(raw)
        message = str(error.value)
        assert "API_KEYS" in message and entry in message, raw
        assert "length" in message, raw
        for secret in (TEACHER_KEY, OFFICE_KEY, "teacher-without-colon"):
            assert secret not in message, raw


def test_identify_returns_the_client_only_for_a_matching_key_and_hides_keys(
    monkeypatch,
):
    keys = parse_api_keys(f"teacher:{TEACHER_KEY},office:{OFFICE_KEY}")
    for presented in ("wrong-key-0000000000", None, "", "clave-ñandú-0123456"):
        assert keys.identify(presented) is None, presented
    assert TEACHER_KEY not in repr(keys) and OFFICE_KEY not in repr(keys)

    calls = []
    real_compare = hmac.compare_digest

    def spy(left, right):
        calls.append((type(left), type(right)))
        return real_compare(left, right)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    assert keys.identify(TEACHER_KEY) == "teacher"
    # Compara contra todas las claves, sin cortar en la primera que coincide.
    assert len(calls) == 2
    assert all(kinds == (bytes, bytes) for kinds in calls)


def test_rate_limiter_allows_the_exact_limit_then_reports_retry_after():
    clock = ManualClock()
    limiter = RateLimiter(2, clock)
    assert limiter.check("teacher") is None
    clock.advance(10)
    assert limiter.check("teacher") is None
    clock.advance(5)
    assert limiter.check("teacher") == 45
    clock.advance(44.5)
    assert limiter.check("teacher") == 1
    clock.advance(1)
    assert limiter.check("teacher") is None


def test_rate_limiter_keeps_clients_apart_and_rejected_requests_take_no_place():
    clock = ManualClock()
    limiter = RateLimiter(1, clock)
    assert limiter.check("teacher") is None
    assert limiter.check("office") is None
    clock.advance(30)
    assert limiter.check("teacher") == 30
    clock.advance(30.5)
    # Si el rechazo de t=30 contara, este pedido seguiría bloqueado.
    assert limiter.check("teacher") is None
    clock.advance(0.5)
    assert limiter.check("teacher") == 60


def test_rate_limiter_admits_exactly_the_limit_from_many_threads():
    limiter = RateLimiter(50, ManualClock())
    results = []
    lock = threading.Lock()

    def worker():
        for _ in range(10):
            outcome = limiter.check("teacher")
            with lock:
                results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 200
    assert results.count(None) == 50
