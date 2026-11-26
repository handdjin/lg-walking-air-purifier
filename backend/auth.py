import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

REGION = "ap-southeast-2"
USER_POOL_ID = "ap-southeast-2_d0fO5MQej"
CLIENT_ID = "j31cu1d9h0giauttffmoq8vqm"

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

jwks_client = PyJWKClient(JWKS_URL)
security = HTTPBearer(auto_error=False)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=ISSUER,
            options={
                "verify_aud": False,
                "require": ["exp", "iss", "sub", "token_use", "client_id"],
            },
        )

        if payload.get("token_use") != "access":
            raise ValueError("Invalid token type")

        if payload.get("client_id") != CLIENT_ID:
            raise ValueError("Invalid client ID")

        return payload

    except (jwt.PyJWTError, ValueError) as e:
        print("JWT verification failed:", type(e).__name__)
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    