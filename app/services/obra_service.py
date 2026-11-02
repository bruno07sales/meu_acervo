from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument

from app.core.database import obras_collection
from app.domain.roles import UserRole, is_internal_role
from app.domain.status import ApprovalStatus
from app.schemas.obra_schema import ObraListResponseSchema, ObraResponseSchema
from app.services import imagem_service
from app.utils.object_id import object_id

UNSET = object()


# Devolve o timestamp UTC usado para criação, atualização e aprovação de obras.
def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


# Deriva um timestamp coerente para documentos legados a partir do ObjectId ou do momento atual.
def _timestamp_legado(documento: dict) -> datetime:
    identificador = documento.get("_id")
    if hasattr(identificador, "generation_time"):
        return identificador.generation_time
    return _agora_utc()


# Indica se o documento de obra foi criado antes do fluxo atual e ainda precisa de migração.
def obra_eh_legada(documento: dict) -> bool:
    return any(
        campo not in documento
        for campo in (
            "status_aprovacao",
            "visivel_publicamente",
            "criado_em",
            "atualizado_em",
        )
    )


# Normaliza documentos legados para manter compatibilidade de leitura antes da migração definitiva.
def normalizar_documento_obra(documento: dict) -> dict:
    normalizado = dict(documento)
    timestamp_base = _timestamp_legado(normalizado)
    normalizado.setdefault("owner_id", None)
    normalizado.setdefault("status_aprovacao", ApprovalStatus.APROVADA.value)
    normalizado.setdefault("visivel_publicamente", True)
    normalizado.setdefault("aprovado_por", None)
    normalizado.setdefault("aprovado_em", None)
    normalizado.setdefault("motivo_rejeicao", None)
    normalizado.setdefault("criado_em", timestamp_base)
    normalizado.setdefault("atualizado_em", normalizado.get("criado_em", timestamp_base))
    return normalizado


# Valida se a obra existe e devolve seu id serializado para reuso em outros fluxos.
def validar_obra_existente(obra_id: str) -> str:
    obra = obras_collection.find_one({"_id": object_id(obra_id)})
    if not obra:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    return str(obra["_id"])


# Busca o documento bruto da obra para checagens de autorização e aprovação.
def obter_documento_obra(obra_id: str) -> dict | None:
    documento = obras_collection.find_one({"_id": object_id(obra_id)})
    if not documento:
        return None
    return normalizar_documento_obra(documento)


# Indica se a obra já pode ser exibida publicamente na aplicação.
def obra_esta_publicada(obra: dict) -> bool:
    obra = normalizar_documento_obra(obra)
    return (
        obra.get("status_aprovacao", ApprovalStatus.PENDENTE.value)
        == ApprovalStatus.APROVADA.value
        and obra.get("visivel_publicamente", False) is True
    )


# Verifica se o usuário pode visualizar uma obra considerando papel, dono e publicação.
def usuario_pode_visualizar_obra(usuario: dict, obra: dict) -> bool:
    role = usuario.get("role")
    if is_internal_role(role):
        return True
    if obra_esta_publicada(obra):
        return True
    return str(obra.get("owner_id")) == str(usuario.get("_id"))


# Verifica se o usuário pode editar uma obra considerando papéis internos e propriedade.
def usuario_pode_editar_obra(usuario: dict, obra: dict) -> bool:
    role = usuario.get("role")
    if is_internal_role(role):
        return True
    return role == UserRole.COLECIONADOR_NEGOCIADOR.value and str(
        obra.get("owner_id")
    ) == str(usuario.get("_id"))


# Centraliza a regra de paginação para manter as listagens de obras consistentes.
def busca_paginacao(
    collection,
    filtro: dict,
    page: int,
    limit: int,
    sort: list[tuple[str, int]],
) -> ObraListResponseSchema:
    page = max(page, 1)
    limit = max(limit, 1)
    skip = (page - 1) * limit

    total = collection.count_documents(filtro)
    cursor = collection.find(filtro).sort(sort).skip(skip).limit(limit)
    return ObraListResponseSchema.from_documents(
        item_schema=ObraResponseSchema,
        documents=(normalizar_documento_obra(documento) for documento in cursor),
        page=page,
        limit=limit,
        total=total,
    )


# Monta o filtro textual e estrutural básico reutilizado nas listagens de obras.
def _filtro_base_obras(
    q: str | None = None,
    autor: str | None = None,
    ano: int | None = None,
) -> dict:
    filtro: dict = {}
    if q:
        regex = {"$regex": q, "$options": "i"}
        filtro["$or"] = [
            {"titulo": regex},
            {"descricao": regex},
            {"autor": regex},
        ]
    if autor:
        filtro["autor"] = {"$regex": autor, "$options": "i"}
    if ano is not None:
        filtro["ano"] = ano
    return filtro


# Monta o filtro que considera obras publicadas no fluxo novo e documentos legados ainda não migrados.
def _filtro_publicacao() -> dict:
    return {
        "$or": [
            {
                "status_aprovacao": ApprovalStatus.APROVADA.value,
                "visivel_publicamente": True,
            },
            {"status_aprovacao": {"$exists": False}},
            {"visivel_publicamente": {"$exists": False}},
        ]
    }


# Monta o filtro que identifica obras legadas para revisão administrativa ou migração.
def _filtro_obras_legadas() -> dict:
    return {
        "$or": [
            {"status_aprovacao": {"$exists": False}},
            {"visivel_publicamente": {"$exists": False}},
            {"criado_em": {"$exists": False}},
            {"atualizado_em": {"$exists": False}},
        ]
    }


# Lista apenas os identificadores das obras visíveis para o usuário atual sem impor paginação artificial.
def listar_ids_obras_visiveis(
    role: str,
    usuario_id: str | None = None,
) -> list[str]:
    if is_internal_role(role):
        documentos = obras_collection.find({}, {"_id": 1})
        return [str(documento["_id"]) for documento in documentos]

    filtro_publico = _filtro_publicacao()
    if role == UserRole.COLECIONADOR_NEGOCIADOR.value and usuario_id is not None:
        filtro = {"$or": [filtro_publico, {"owner_id": usuario_id}]}
    else:
        filtro = filtro_publico

    documentos = obras_collection.find(filtro, {"_id": 1})
    return [str(documento["_id"]) for documento in documentos]


# Cria uma nova obra preenchendo autoria, status de aprovação e timestamps de controle.
def criar_obra(
    titulo: str,
    descricao: str | None = None,
    autor: str | None = None,
    ano: int | None = None,
    destinatario: str | None = None,
    tipo_obra: str | None = None,
    data: str | None = None,
    local_expedicao: str | None = None,
    preco: float | None = None,
    observacoes: str | None = None,
    imagem_ou_digitalizacao: str | None = None,
    owner_id: str | None = None,
    status_aprovacao: str | ApprovalStatus = ApprovalStatus.PENDENTE,
    visivel_publicamente: bool = False,
) -> ObraResponseSchema:
    agora = _agora_utc()
    documento = {
        "titulo": titulo,
        "descricao": descricao,
        "autor": autor,
        "destinatario": destinatario,
        "tipo_obra": tipo_obra,
        "data": data,
        "local_expedicao": local_expedicao,
        "preco": preco,
        "observacoes": observacoes,
        "imagem_ou_digitalizacao": imagem_ou_digitalizacao,
        "ano": ano,
        "owner_id": owner_id,
        "status_aprovacao": (
            status_aprovacao.value
            if isinstance(status_aprovacao, ApprovalStatus)
            else str(status_aprovacao)
        ),
        "visivel_publicamente": visivel_publicamente,
        "aprovado_por": None,
        "aprovado_em": None,
        "motivo_rejeicao": None,
        "criado_em": agora,
        "atualizado_em": agora,
    }
    resultado = obras_collection.insert_one(documento)
    documento["_id"] = resultado.inserted_id
    return ObraResponseSchema.from_document(documento)


# Lista obras com filtros opcionais e regras específicas para publicação e propriedade.
def listar_obras(
    page: int = 1,
    limit: int = 10,
    q: str | None = None,
    autor: str | None = None,
    ano: int | None = None,
    owner_id: str | None = None,
    include_owner_pending: bool = False,
    somente_publicadas: bool = False,
) -> ObraListResponseSchema:
    base = _filtro_base_obras(q=q, autor=autor, ano=ano)
    if somente_publicadas:
        publicado = {"$and": [base, _filtro_publicacao()]} if base else _filtro_publicacao()
        if owner_id and include_owner_pending:
            filtro = {"$or": [publicado, {**base, "owner_id": owner_id}]}
        else:
            filtro = publicado
    else:
        filtro = {**base}
        if owner_id and not include_owner_pending:
            filtro["owner_id"] = owner_id

    return busca_paginacao(
        obras_collection,
        filtro,
        page=page,
        limit=limit,
        sort=[("criado_em", -1)],
    )


# Busca uma obra específica pelo identificador e serializa o documento de resposta.
def obter_obra(obra_id: str) -> ObraResponseSchema | None:
    obra = obter_documento_obra(obra_id)
    if not obra:
        return None
    return ObraResponseSchema.from_document(obra)


# Atualiza apenas os campos enviados e permite controlar o ciclo de aprovação da obra.
def atualizar_obra(
    obra_id: str,
    titulo: str | None = None,
    descricao: str | None = None,
    autor: str | None = None,
    ano: int | None = None,
    destinatario: str | None = None,
    tipo_obra: str | None = None,
    data: str | None = None,
    local_expedicao: str | None = None,
    preco: float | None = None,
    observacoes: str | None = None,
    imagem_ou_digitalizacao: str | None = None,
    status_aprovacao: str | ApprovalStatus | object = UNSET,
    visivel_publicamente: bool | object = UNSET,
    aprovado_por: str | None | object = UNSET,
    aprovado_em: datetime | None | object = UNSET,
    motivo_rejeicao: str | None | object = UNSET,
) -> ObraResponseSchema | None:
    atualizacoes = {
        chave: valor
        for chave, valor in {
            "titulo": titulo,
            "descricao": descricao,
            "autor": autor,
            "destinatario": destinatario,
            "tipo_obra": tipo_obra,
            "data": data,
            "local_expedicao": local_expedicao,
            "preco": preco,
            "observacoes": observacoes,
            "imagem_ou_digitalizacao": imagem_ou_digitalizacao,
            "ano": ano,
        }.items()
        if valor is not None
    }
    if status_aprovacao is not UNSET:
        atualizacoes["status_aprovacao"] = (
            status_aprovacao.value
            if isinstance(status_aprovacao, ApprovalStatus)
            else status_aprovacao
        )
    if visivel_publicamente is not UNSET:
        atualizacoes["visivel_publicamente"] = visivel_publicamente
    if aprovado_por is not UNSET:
        atualizacoes["aprovado_por"] = aprovado_por
    if aprovado_em is not UNSET:
        atualizacoes["aprovado_em"] = aprovado_em
    if motivo_rejeicao is not UNSET:
        atualizacoes["motivo_rejeicao"] = motivo_rejeicao

    if not atualizacoes:
        return obter_obra(obra_id)

    atualizacoes["atualizado_em"] = _agora_utc()
    resultado = obras_collection.find_one_and_update(
        {"_id": object_id(obra_id)},
        {"$set": atualizacoes},
        return_document=ReturnDocument.AFTER,
    )
    if not resultado:
        return None
    return ObraResponseSchema.from_document(resultado)


# Lista as obras que ainda aguardam aprovação administrativa.
def listar_obras_pendentes() -> list[ObraResponseSchema]:
    documentos = obras_collection.find(
        {"status_aprovacao": ApprovalStatus.PENDENTE.value}
    ).sort([("criado_em", 1)])
    return ObraResponseSchema.from_documents(
        (normalizar_documento_obra(documento) for documento in documentos)
    )


# Lista as obras legadas que ainda não receberam os novos campos obrigatórios do fluxo de aprovação.
def listar_obras_legadas() -> list[ObraResponseSchema]:
    documentos = obras_collection.find(_filtro_obras_legadas()).sort([("_id", 1)])
    return ObraResponseSchema.from_documents(
        (normalizar_documento_obra(documento) for documento in documentos)
    )


# Aprova uma obra e a libera para exibição pública.
def aprovar_obra(obra_id: str, admin_id: str) -> ObraResponseSchema | None:
    return atualizar_obra(
        obra_id,
        status_aprovacao=ApprovalStatus.APROVADA,
        visivel_publicamente=True,
        aprovado_por=admin_id,
        aprovado_em=_agora_utc(),
        motivo_rejeicao=None,
    )


# Rejeita uma obra e a mantém fora da exibição pública até nova revisão.
def rejeitar_obra(
    obra_id: str,
    admin_id: str,
    motivo_rejeicao: str | None = None,
) -> ObraResponseSchema | None:
    return atualizar_obra(
        obra_id,
        status_aprovacao=ApprovalStatus.REJEITADA,
        visivel_publicamente=False,
        aprovado_por=admin_id,
        aprovado_em=_agora_utc(),
        motivo_rejeicao=motivo_rejeicao,
    )


# Remove a obra e limpa antes as imagens associadas para evitar dados órfãos.
def excluir_obra(obra_id: str) -> bool:
    obra_object_id = object_id(obra_id)
    imagem_service.remover_por_obra(str(obra_object_id))
    resultado = obras_collection.delete_one({"_id": obra_object_id})
    return resultado.deleted_count > 0
