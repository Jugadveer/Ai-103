"""
Sessions.

The cookie carries the user id, an expiry and a signature, and nothing
else. There is no session table: the server does not have to remember
anything to trust the cookie back, it only has to still hold the key.

    <user id>.<expiry unix seconds>.<hmac sha256 hex>

Tampering with the id changes the signature, and the signature cannot be
recomputed without SECRET_KEY. The expiry is inside the signed part, so
it cannot be pushed forward either.

The cookie is httponly, so page scripts cannot read it and an injected
script cannot steal it; samesite=lax, so another site cannot ride on it;
and secure whenever the app is served over https.
"""
import hmac
import secrets
import time
from hashlib import sha256

from fastapi import Request, Response

from app import config
from app.core import logging as log
from app.store import db, users

COOKIE = "hc_session"

# A missing key would be an easy thing to shrug at, so it is worth being
# clear about what it costs: without one, a restart signs everybody out,
# and on a host that runs several instances people are signed out at
# random as their requests land on different ones. Fine locally, not fine
# anywhere else, so it is logged loudly rather than silently patched over.
_SECRET = config.SECRET_KEY
if not _SECRET:
    _SECRET = secrets.token_hex(32)
    log.info("secret_key_generated",
             note="SECRET_KEY is not set, so sessions last only as long as "
                  "this process. Set it in the environment before deploying.")


def _sign(payload: str) -> str:
    return hmac.new(_SECRET.encode(), payload.encode(), sha256).hexdigest()


def make_token(user_id: int) -> str:
    expires = int(time.time()) + config.SESSION_DAYS * 86400
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> int | None:
    """Return the user id, or None if the token is bad or out of date."""
    try:
        user_id, expires, signature = token.split(".")
        payload = f"{user_id}.{expires}"
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    if int(expires) < time.time():
        return None
    return int(user_id)


def set_cookie(response: Response, request: Request, user_id: int) -> None:
    response.set_cookie(
        COOKIE, make_token(user_id),
        max_age=config.SESSION_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/")


async def current_user(request: Request) -> dict | None:
    """
    Resolve the signed-in user and point storage at them.

    This is async on purpose. A sync dependency runs in its own worker
    thread, and the context variable it sets there would not be visible
    to the endpoint; an async one shares the request's context, and the
    threadpool copies that context when it runs a sync endpoint.
    """
    db.CURRENT_USER.set(0)
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    user_id = read_token(token)
    if user_id is None:
        return None
    user = users.find_by_id(user_id)
    if user is None:          # account deleted since the cookie was issued
        return None
    db.CURRENT_USER.set(user["id"])
    return users.public(user)
