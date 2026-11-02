from passlib.hash import sha256_crypt
from pymongo.errors import PyMongoError

from app.core.config import settings
from app.domain.roles import UserRole
from app.domain.status import UserStatus
from app.services import usuario_service


# Gera o hash seguro de uma senha em texto puro.
def _hash_senha(senha: str) -> str:
    return sha256_crypt.hash(senha)


# Verifica se a senha informada corresponde ao hash armazenado.
def _senha_confere(senha_fornecida: str, senha_armazenada: str) -> bool:
    try:
        return sha256_crypt.verify(senha_fornecida, senha_armazenada)
    except Exception:
        return False


# Detecta se a senha armazenada já está em formato hash para suportar migração de legados.
def _senha_em_hash(senha_armazenada: str) -> bool:
    try:
        return sha256_crypt.identify(senha_armazenada)
    except Exception:
        return False


# Verifica se o usuário está ativo e aprovado antes de liberar o acesso autenticado.
def _usuario_pode_fazer_login(usuario: dict) -> bool:
    if not usuario.get("ativo", True):
        return False

    status = usuario.get("status", UserStatus.APROVADO.value)
    return status == UserStatus.APROVADO.value


# Garante um administrador inicial quando o bootstrap estiver habilitado na configuração.
def garantir_admin_bootstrap() -> None:
    if not settings.ENABLE_BOOTSTRAP_ADMIN:
        return

    email = (settings.BOOTSTRAP_ADMIN_EMAIL or "").strip().lower()
    senha = settings.BOOTSTRAP_ADMIN_PASSWORD or ""
    if not email or not senha:
        return

    try:
        if usuario_service.buscar_por_email(email):
            return

        usuario_service.criar_usuario(
            email,
            senha,
            nome=settings.BOOTSTRAP_ADMIN_NAME,
            role=UserRole.ADMIN,
            status=UserStatus.APROVADO,
        )
    except PyMongoError:
        return


# Autentica um usuário por e-mail e senha com suporte a migração de senhas legadas.
def autenticar_usuario(email: str, senha: str):
    usuario = usuario_service.buscar_por_email(email)
    if not usuario:
        return None

    senha_armazenada = usuario.get("senha")
    if not senha_armazenada:
        return None

    if _senha_em_hash(senha_armazenada):
        if not _senha_confere(senha, senha_armazenada):
            return None
        if not _usuario_pode_fazer_login(usuario):
            return None
        return usuario

    if senha != senha_armazenada:
        return None

    novo_hash = _hash_senha(senha)
    usuario_service.atualizar_senha_usuario(usuario["_id"], novo_hash)
    usuario["senha"] = novo_hash
    if not _usuario_pode_fazer_login(usuario):
        return None

    return usuario
