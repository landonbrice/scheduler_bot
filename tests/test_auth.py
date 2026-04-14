import hashlib
import hmac
import time
from urllib.parse import urlencode
import pytest
from backend.auth import verify_init_data, InitDataInvalid


BOT_TOKEN = "123456:TESTTOKEN"


def _sign(data: dict, token: str = BOT_TOKEN) -> str:
    """Build a valid initData string the way Telegram's client would."""
    pairs = sorted((k, v) for k, v in data.items() if k != "hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in pairs)
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**data, "hash": h})


def test_verify_returns_user_on_valid_data():
    now = int(time.time())
    init = _sign({"auth_date": str(now), "user": '{"id":42,"first_name":"L"}', "query_id": "q"})
    result = verify_init_data(init, BOT_TOKEN)
    assert result.user_id == 42


def test_rejects_tampered_hash():
    now = int(time.time())
    init = _sign({"auth_date": str(now), "user": '{"id":42}'})
    tampered = init.replace("id%22%3A42", "id%22%3A99")
    with pytest.raises(InitDataInvalid):
        verify_init_data(tampered, BOT_TOKEN)


def test_rejects_expired_auth_date():
    old = int(time.time()) - 60 * 60 * 25  # 25h ago
    init = _sign({"auth_date": str(old), "user": '{"id":1}'})
    with pytest.raises(InitDataInvalid):
        verify_init_data(init, BOT_TOKEN, max_age_seconds=86400)


def test_rejects_missing_hash():
    with pytest.raises(InitDataInvalid):
        verify_init_data("auth_date=1&user=%7B%22id%22%3A1%7D", BOT_TOKEN)


def test_rejects_wrong_bot_token():
    now = int(time.time())
    init = _sign({"auth_date": str(now), "user": '{"id":1}'})
    with pytest.raises(InitDataInvalid):
        verify_init_data(init, "999:WRONG")
