from fastapi import APIRouter, HTTPException, Response

from app.domain.roles import UserRole
from app.schemas.usuario_schema import (
    LoginInput,
    UsuarioCreateInput,
    UsuarioCreateResponse,
)
from app.services import auditoria_service, jwt_service
from app.services.auth_service import autenticar_usuario
from app.services.usuario_service import criar_pre_cadastro_locatario

router = APIRouter(prefix="/auth", tags=["auth"])


# Cria um alias semântico para o fluxo público de solicitação do perfil de locatário.
@router.post("/pre-cadastro-locatario", response_model=UsuarioCreateResponse)
def pre_cadastro_locatario(data: UsuarioCreateInput):
    user = criar_pre_cadastro_locatario(data.email, data.senha, nome=data.nome)
    if not user:
        raise HTTPException(
            status_code=409, detail="Por favor, tente com outro usuário ou e-mail"
        )

    auditoria_service.registrar_evento(
        "pre_cadastro_locatario",
        alvo_id=str(user["_id"]),
        metadata={"role": UserRole.LOCATARIO.value},
    )
    return {
        "message": "Pré-cadastro realizado com sucesso",
        "role": user["role"],
        "status": user["status"],
    }


# Autentica o usuário, emite JWT e grava a sessão no cookie HTTP-only.
@router.post("/login")
def login(data: LoginInput, response: Response):
    user = autenticar_usuario(data.email, data.senha)
    if not user:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = jwt_service.criar_token(
        {"sub": str(user["_id"]), "role": user.get("role", UserRole.LOCATARIO.value)}
    )
    jwt_service.definir_cookie_autenticacao(response, token)
    auditoria_service.registrar_evento(
        "login",
        ator_id=str(user["_id"]),
        alvo_id=str(user["_id"]),
        metadata={"role": user.get("role")},
    )
    return {"message": "Login efetuado"}


# Remove o cookie de autenticação do usuário atual, efetivando o logout.
@router.post("/logout")
def logout(response: Response):
    jwt_service.limpar_cookie_autenticacao(response)
    return {"message": "Logout efetuado"}
