from __future__ import annotations
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataInvalid(ValueError):
    pass


@dataclass
class TelegramUser:
    user_id: int
    first_name: str
    username: str | None


def verify_init_data(init_data: str, bot_token: str, max_age_seconds: int = 0) -> TelegramUser:
    """Validate a Telegram Mini App initData string.

    Raises InitDataInvalid on any failure. Returns the parsed user on success.
    """
    if not init_data:
        raise InitDataInvalid("empty initData")

    pairs = parse_qsl(init_data, strict_parsing=False)
    data = dict(pairs)

    received_hash = data.pop("hash", None)
    if not received_hash:
        raise InitDataInvalid("missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed, received_hash):
        raise InitDataInvalid("hash mismatch")

    auth_date = int(data.get("auth_date", "0"))
    if auth_date <= 0:
        raise InitDataInvalid("auth_date missing")
    if max_age_seconds > 0 and (time.time() - auth_date) > max_age_seconds:
        raise InitDataInvalid("auth_date expired")

    user_json = data.get("user")
    if not user_json:
        raise InitDataInvalid("missing user")
    user = json.loads(user_json)
    return TelegramUser(
        user_id=int(user["id"]),
        first_name=user.get("first_name", ""),
        username=user.get("username"),
    )
