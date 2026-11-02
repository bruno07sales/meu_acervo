from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from jose import JWTError, jwt
from starlette.responses import Response

from app.core.config import settings
from app.domain.status import UserStatus
from app.services import usuario_service


# Devolve o instante de expiração do token a partir da configuração central da aplicação
def _expiracao_token() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_EXP_SECONDS)


# Cria um token JWT com os dados informados e metadados temporais para validação segura.
def criar_token(data: dict) -> str:
    agora = datetime.now(timezone.utc)
    payload = {
        **data,
        "iat": int(agora.timestamp()),
        "exp": int(_expiracao_token().timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


# Centraliza a política do cookie de autenticação para manter login e logout consistentes.
def definir_cookie_autenticacao(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE,
        max_age=settings.COOKIE_MAX_AGE,
        path=settings.COOKIE_PATH,
    )


# Remove o mesmo cookie usando o mesmo path configurado no login.
def limpar_cookie_autenticacao(response: Response) -> None:
    response.delete_cookie(
        key=settings.COOKIE_NAME,
        path=settings.COOKIE_PATH,
    )


# Decodifica o JWT e reaproveita a mesma configuração usada na emissão do token.
def decodificar_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


# Recupera o usuário atual a partir do cookie, validando o token e recarregando o usuário no banco.
def get_current_user(request: Request) -> dict:
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")

    try:
        payload = decodificar_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    usuario_id = payload.get("sub")
    if not usuario_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    usuario = usuario_service.buscar_por_id(str(usuario_id))
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if not usuario.get("ativo", True):
        raise HTTPException(status_code=403, detail="Usuário inativo")
    if usuario.get("status", UserStatus.APROVADO.value) != UserStatus.APROVADO.value:
        raise HTTPException(status_code=403, detail="Usuário sem aprovação de acesso")

    return usuario
