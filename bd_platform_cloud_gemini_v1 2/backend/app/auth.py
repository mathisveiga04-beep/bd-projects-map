import os
from typing import Optional
import jwt
from fastapi import Header, HTTPException, status

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
# Verification optionnelle de l'audience (defense en profondeur).
# Laissee vide par defaut pour ne casser aucun flux existant : definir
# SUPABASE_JWT_AUD=authenticated sur Render pour l'activer (valeur standard Supabase).
SUPABASE_JWT_AUD = os.getenv("SUPABASE_JWT_AUD", "").strip()

def verify_supabase_jwt(authorization: Optional[str] = Header(default=None)) -> dict:
    """Verify Supabase JWT from Authorization: Bearer <token> header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_JWT_SECRET not configured on server",
        )
    decode_kwargs = {"algorithms": ["HS256"], "options": {"verify_exp": True}}
    if SUPABASE_JWT_AUD:
        decode_kwargs["audience"] = SUPABASE_JWT_AUD
    else:
        # Comportement historique conserve : on ne verifie pas l'audience.
        decode_kwargs["options"]["verify_aud"] = False
    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, **decode_kwargs)
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )

def get_user_id(payload: dict) -> str:
    """Extract Supabase user UUID from JWT payload (sub claim)."""
    return payload.get("sub", "")

def get_user_role(payload: dict) -> str:
    """Extract user role from app_metadata."""
    # SECURITE: lire le role uniquement depuis app_metadata (controle serveur),
    # jamais depuis user_metadata qui est modifiable par l'utilisateur (escalade de privileges).
    return payload.get("app_metadata", {}).get("role") or "user"
