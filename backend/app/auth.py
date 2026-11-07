"""Login admin via OIDC (Authentik) — même principe que challenges/locations.

Flux authorization code + PKCE. Le code est échangé côté serveur (secret client), puis
l'identité est lue sur l'endpoint userinfo : pas de validation JWT locale nécessaire.
State + verifier voyagent dans un cookie signé de courte durée ; la session admin est un
cookie signé (itsdangerous), sans stockage serveur.
"""

import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .config import settings

router = APIRouter(prefix="/api/auth")

SESSION_COOKIE = "loto_session"
SESSION_MAX_AGE = 12 * 3600
FLOW_COOKIE = "loto_oidc_flow"          # préfixe : le nom réel est suffixé par le state
FLOW_MAX_AGE = 600


def flow_cookie(state: str) -> str:
    """Nom du cookie de flux, propre à un state : le navigateur peut en garder plusieurs."""
    return f"{FLOW_COOKIE}_{state}"

_session = URLSafeTimedSerializer(settings.session_secret, salt="loto-session")
_flow = URLSafeTimedSerializer(settings.session_secret, salt="loto-oidc-flow")
_discovery: dict | None = None


async def discovery() -> dict:
    global _discovery
    if _discovery is None:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration")
            r.raise_for_status()
            _discovery = r.json()
    return _discovery


def redirect_uri() -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/auth/callback"


def safe_next(path: str | None) -> str:
    return path if path and path.startswith("/") and not path.startswith("//") else "/admin"


def cookie_kwargs() -> dict:
    return {"httponly": True, "samesite": "lax", "secure": settings.public_base_url.startswith("https://")}


def current_user(request: Request) -> str | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return _session.loads(token, max_age=SESSION_MAX_AGE)["u"]
    except (BadSignature, KeyError, TypeError):
        return None


def admin(request: Request) -> str:
    """Dépendance FastAPI des routes /api/admin/* : session valide + utilisateur autorisé."""
    user = current_user(request)
    if not user:
        raise HTTPException(401, "Non authentifié.")
    # revérifié à chaque requête : retirer quelqu'un de la liste coupe l'accès immédiatement
    if user not in settings.admin_user_list:
        raise HTTPException(403, "Accès refusé.")
    return user


@router.get("/login")
async def login(next: str = "/admin"):
    if not (settings.oidc_client_id and settings.oidc_client_secret):
        raise HTTPException(503, "OIDC non configuré.")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": redirect_uri(),
        "scope": "openid profile email",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    resp = RedirectResponse(f"{(await discovery())['authorization_endpoint']}?{urlencode(params)}", 302)
    resp.set_cookie(flow_cookie(state), _flow.dumps({"s": state, "v": verifier, "n": safe_next(next)}),
                    max_age=FLOW_MAX_AGE, path="/api/auth", **cookie_kwargs())
    return resp


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    try:
        flow = _flow.loads(request.cookies.get(flow_cookie(state or ""), ""), max_age=FLOW_MAX_AGE)
    except BadSignature:
        flow = None
    if error:
        return RedirectResponse(f"/admin?login_error={error}", 302)
    if not code or not flow or flow.get("s") != state:
        raise HTTPException(400, "Requête de connexion invalide ou expirée.")

    disc = await discovery()
    async with httpx.AsyncClient(timeout=10) as c:
        tok = await c.post(disc["token_endpoint"], data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "code_verifier": flow["v"],
        })
        if tok.status_code != 200:
            raise HTTPException(502, "Échec de l'échange du code OIDC.")
        ui = await c.get(disc["userinfo_endpoint"],
                         headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        if ui.status_code != 200:
            raise HTTPException(502, "Échec de la lecture du profil OIDC.")
    info = ui.json()
    username = info.get("preferred_username") or info.get("sub")

    if username not in settings.admin_user_list:
        resp = RedirectResponse("/admin?login_error=forbidden", 302)
    else:
        resp = RedirectResponse(flow["n"], 302)
        resp.set_cookie(SESSION_COOKIE, _session.dumps({"u": username}),
                        max_age=SESSION_MAX_AGE, path="/", **cookie_kwargs())
    resp.delete_cookie(flow_cookie(state or ""), path="/api/auth")
    return resp


@router.get("/me")
def me(request: Request):
    user = current_user(request)
    return {"authenticated": bool(user), "username": user, "allowed": user in settings.admin_user_list}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}
