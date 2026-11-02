from datetime import datetime, timezone

from passlib.hash import sha256_crypt

from app.core.database import usuarios_collection
from app.domain.roles import UserRole, is_admin_managed_role
from app.domain.status import UserStatus
from app.utils.object_id import object_id


# Devolve o timestamp UTC usado para campos de auditoria e controle de acesso.
def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


# Gera o hash seguro da senha informada antes de persistir o usuário.
def _hash_senha(senha: str) -> str:
    return sha256_crypt.hash(senha)


# Normaliza o e-mail para evitar duplicidade por diferença de caixa ou espaços.
def _normalizar_email(email: str) -> str:
    return email.strip().lower()


# Normaliza o papel do usuário para o valor canônico salvo no banco.
def _normalizar_role(role: str | UserRole) -> str:
    return role.value if isinstance(role, UserRole) else str(role).strip().lower()


# Normaliza o status do usuário para o valor canônico salvo no banco.
def _normalizar_status(status: str | UserStatus) -> str:
    return status.value if isinstance(status, UserStatus) else str(status).strip().lower()

_LEGACY_ROLE_ALIASES = {
    "user": UserRole.LOCATARIO.value,
    "usuario": UserRole.LOCATARIO.value,
}


# Normaliza documentos antigos para que leituras administrativas continuem compatíveis com os schemas atuais.
def normalizar_documento_usuario(documento: dict | None) -> dict | None:
    if documento is None:
        return None

    normalizado = dict(documento)
    role = normalizado.get("role")
    if role is None:
        normalizado["role"] = UserRole.LOCATARIO.value
    else:
        role_normalizada = _normalizar_role(role)
        normalizado["role"] = _LEGACY_ROLE_ALIASES.get(role_normalizada, role_normalizada)

    status = normalizado.get("status")
    normalizado["status"] = (
        _normalizar_status(status) if status is not None else UserStatus.APROVADO.value
    )
    normalizado.setdefault("ativo", True)
    normalizado.setdefault("perfil_monitorado_ids", [])
    normalizado.setdefault("nome", None)
    return normalizado

# Centraliza a busca por e-mail para toda a aplicação.
def buscar_por_email(email: str) -> dict | None:
    return normalizar_documento_usuario(
        usuarios_collection.find_one({"email": _normalizar_email(email)})
    )


# Busca um usuário pelo identificador para autenticação, autorização e administração.
def buscar_por_id(usuario_id: str) -> dict | None:
    return normalizar_documento_usuario(
        usuarios_collection.find_one({"_id": object_id(usuario_id)})
    )


# Atualiza a senha do usuário em um único ponto da camada de persistência.
def atualizar_senha_usuario(usuario_id, senha_hash: str) -> None:
    usuarios_collection.update_one(
        {"_id": usuario_id},
        {"$set": {"senha": senha_hash, "atualizado_em": _agora_utc()}},
    )


# Atualiza o status de acesso do usuário e registra quem realizou a transição.
def atualizar_status_usuario(
    usuario_id: str,
    status: str | UserStatus,
    aprovado_por: str | None = None,
) -> dict | None:
    atualizacao = {
        "status": _normalizar_status(status),
        "atualizado_em": _agora_utc(),
    }
    if aprovado_por is not None:
        atualizacao["aprovado_por"] = object_id(aprovado_por)
        atualizacao["aprovado_em"] = _agora_utc()

    usuarios_collection.update_one(
        {"_id": object_id(usuario_id)},
        {"$set": atualizacao},
    )
    return buscar_por_id(usuario_id)


# Cria o documento base do usuário com campos de controle de acesso e auditoria.
def _montar_documento_usuario(
    email: str,
    senha: str,
    nome: str | None,
    role: str | UserRole,
    status: str | UserStatus,
    ativo: bool = True,
    aprovado_por: str | None = None,
) -> dict:
    agora = _agora_utc()
    documento = {
        "email": _normalizar_email(email),
        "senha": _hash_senha(senha),
        "role": _normalizar_role(role),
        "status": _normalizar_status(status),
        "ativo": ativo,
        "perfil_monitorado_ids": [],
        "criado_em": agora,
        "atualizado_em": agora,
    }
    if nome is not None:
        documento["nome"] = nome
    if aprovado_por is not None:
        documento["aprovado_por"] = object_id(aprovado_por)
        documento["aprovado_em"] = agora
    return documento


# Cria um usuário com parâmetros explícitos para suportar bootstrap, aprovação e cadastros internos.
def criar_usuario(
    email: str,
    senha: str,
    nome: str | None = None,
    role: str | UserRole = UserRole.LOCATARIO,
    status: str | UserStatus = UserStatus.PENDENTE,
    ativo: bool = True,
    aprovado_por: str | None = None,
):
    email_normalizado = _normalizar_email(email)
    if buscar_por_email(email_normalizado):
        return None

    documento = _montar_documento_usuario(
        email=email_normalizado,
        senha=senha,
        nome=nome,
        role=role,
        status=status,
        ativo=ativo,
        aprovado_por=aprovado_por,
    )
    resultado = usuarios_collection.insert_one(documento)
    documento["_id"] = resultado.inserted_id
    return documento


# Cria o pré-cadastro público do locatário aguardando aprovação administrativa.
def criar_pre_cadastro_locatario(email: str, senha: str, nome: str | None = None):
    return criar_usuario(
        email=email,
        senha=senha,
        nome=nome,
        role=UserRole.LOCATARIO,
        status=UserStatus.PENDENTE,
    )


# Cria usuários internos ou negociadores diretamente pelo painel administrativo.
def criar_usuario_admin(
    email: str,
    senha: str,
    nome: str | None,
    role: str | UserRole,
    admin_id: str,
):
    role_normalizada = _normalizar_role(role)
    if not is_admin_managed_role(role_normalizada):
        raise ValueError("role inválida para criação administrativa")

    return criar_usuario(
        email=email,
        senha=senha,
        nome=nome,
        role=role_normalizada,
        status=UserStatus.APROVADO,
        aprovado_por=admin_id,
    )


# Lista os usuários que ainda dependem de revisão administrativa.
def listar_usuarios_pendentes() -> list[dict]:
    documentos = usuarios_collection.find({"status": UserStatus.PENDENTE.value}).sort(
        [("criado_em", 1)]
    )
    return [normalizar_documento_usuario(documento) for documento in documentos]


# Lista todos os usuários cadastrados para uso em painéis administrativos.
def listar_usuarios() -> list[dict]:
    documentos = usuarios_collection.find({}).sort([("criado_em", -1), ("email", 1)])
    return [normalizar_documento_usuario(documento) for documento in documentos]


# Atualiza a lista de perfis monitorados por um administrador.
def atualizar_monitoramento_admin(
    admin_id: str,
    usuario_alvo_id: str,
    monitorar: bool,
) -> dict | None:
    operador = "$addToSet" if monitorar else "$pull"
    usuarios_collection.update_one(
        {"_id": object_id(admin_id)},
        {
            operador: {"perfil_monitorado_ids": str(object_id(usuario_alvo_id))},
            "$set": {"atualizado_em": _agora_utc()},
        },
    )
    return buscar_por_id(admin_id)
