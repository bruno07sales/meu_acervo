from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator

from app.core.permissions import require_admin
from app.domain.status import ApprovalStatus, UserStatus
from app.schemas.admin_schema import UsuarioListResponseSchema
from app.schemas.auditoria_schema import (
    EventoAuditoriaListResponseSchema,
    EventoAuditoriaResponse,
)
from app.schemas.obra_schema import ObraListResponseSchema, ObraResponseSchema
from app.schemas.usuario_schema import (
    UsuarioAdminCreateInput,
    UsuarioMonitoramentoInput,
    UsuarioResponseSchema,
    UsuarioStatusResponse,
)
from app.services import aprovacao_service, auditoria_service, usuario_service

router = APIRouter(prefix="/admin", tags=["admin"])


class AtualizarStatusUsuarioBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: UserStatus

    @field_validator("status")
    @classmethod
    def validar_status_permitido(cls, value: UserStatus) -> UserStatus:
        if value not in {UserStatus.APROVADO, UserStatus.REJEITADO}:
            raise ValueError("status invÃ¡lido para atualizaÃ§Ã£o de usuÃ¡rio")
        return value


class AtualizarStatusObraBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApprovalStatus
    motivo_rejeicao: str | None = None

    @field_validator("status")
    @classmethod
    def validar_status_permitido(cls, value: ApprovalStatus) -> ApprovalStatus:
        if value not in {ApprovalStatus.APROVADA, ApprovalStatus.REJEITADA}:
            raise ValueError("status invÃ¡lido para atualizaÃ§Ã£o de obra")
        return value


def _resposta_paginada(schema, item_schema, documentos: list[dict]):
    total = len(documentos)
    return schema.from_documents(
        item_schema=item_schema,
        documents=documentos,
        page=1,
        limit=max(total, 1),
        total=total,
    )


# Cria usuÃ¡rios internos ou negociadores sob controle explÃ­cito do administrador.
@router.post("/usuarios", response_model=UsuarioResponseSchema)
def criar_usuario_admin(
    data: UsuarioAdminCreateInput,
    admin=Depends(require_admin),
):
    try:
        usuario = usuario_service.criar_usuario_admin(
            email=data.email,
            senha=data.senha,
            nome=data.nome,
            role=data.role,
            admin_id=str(admin["_id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not usuario:
        raise HTTPException(status_code=409, detail="E-mail jÃ¡ cadastrado")

    auditoria_service.registrar_evento(
        "usuario_criado_por_admin",
        ator_id=str(admin["_id"]),
        alvo_id=str(usuario["_id"]),
        metadata={"role": usuario["role"]},
    )
    return usuario


# Lista usuÃ¡rios que aguardam aprovaÃ§Ã£o administrativa de acesso.
@router.get("/usuarios/pendentes", response_model=UsuarioListResponseSchema)
def listar_usuarios_pendentes(admin=Depends(require_admin)):
    return _resposta_paginada(
        UsuarioListResponseSchema,
        UsuarioResponseSchema,
        aprovacao_service.listar_usuarios_pendentes(),
    )


# Lista todos os usuÃ¡rios cadastrados para visÃ£o administrativa completa.
@router.get("/usuarios", response_model=UsuarioListResponseSchema)
def listar_usuarios(admin=Depends(require_admin)):
    return _resposta_paginada(
        UsuarioListResponseSchema,
        UsuarioResponseSchema,
        aprovacao_service.listar_usuarios(),
    )


# Aprova ou rejeita um usuÃ¡rio pendente com base no status informado no body.
@router.post(
    "/usuarios/{usuario_id}/status",
    response_model=UsuarioResponseSchema,
    summary="Aprovar ou Rejeitar UsuÃ¡rio",
    description="Atualiza o status de um usuÃ¡rio pendente para `aprovado` ou `rejeitado`.",
)
def atualizar_status_usuario(
    usuario_id: str,
    body: AtualizarStatusUsuarioBody,
    admin=Depends(require_admin),
):
    usuario = aprovacao_service.atualizar_status_usuario(
        usuario_id=usuario_id,
        admin_id=str(admin["_id"]),
        status=body.status.value,
    )
    if not usuario:
        raise HTTPException(status_code=404, detail="UsuÃ¡rio nÃ£o encontrado")
    return usuario


# Ativa ou remove o monitoramento de um perfil especÃ­fico pelo administrador.
@router.post(
    "/usuarios/{usuario_id}/monitoramento",
    response_model=UsuarioStatusResponse,
)
def atualizar_monitoramento_usuario(
    usuario_id: str,
    dados: UsuarioMonitoramentoInput,
    admin=Depends(require_admin),
):
    usuario = usuario_service.atualizar_monitoramento_admin(
        admin_id=str(admin["_id"]),
        usuario_alvo_id=usuario_id,
        monitorar=dados.monitorar,
    )
    if not usuario:
        raise HTTPException(status_code=404, detail="Administrador nÃ£o encontrado")

    auditoria_service.registrar_evento(
        "monitoramento_atualizado",
        ator_id=str(admin["_id"]),
        alvo_id=usuario_id,
        metadata={"monitorar": dados.monitorar},
    )
    return {
        "message": "Monitoramento atualizado com sucesso",
        "status": "ativo" if dados.monitorar else "removido",
    }


# Lista obras ainda pendentes de revisÃ£o administrativa.
@router.get("/obras/pendentes", response_model=ObraListResponseSchema)
def listar_obras_pendentes(admin=Depends(require_admin)):
    return _resposta_paginada(
        ObraListResponseSchema,
        ObraResponseSchema,
        aprovacao_service.listar_obras_pendentes(),
    )


# Lista obras legadas que ainda dependem de migraÃ§Ã£o ou revisÃ£o manual.
@router.get("/obras/legadas", response_model=ObraListResponseSchema)
def listar_obras_legadas(admin=Depends(require_admin)):
    return _resposta_paginada(
        ObraListResponseSchema,
        ObraResponseSchema,
        aprovacao_service.listar_obras_legadas(),
    )


# Aprova ou rejeita uma obra submetida por fluxo dependente de revisÃ£o.
@router.post(
    "/obras/{obra_id}/status",
    response_model=ObraResponseSchema,
    summary="Aprovar Obra ou Rejeitar Obra",
    description="Atualiza o status de uma obra pendente para `aprovada` ou `rejeitada`.",
)
def atualizar_status_obra(
    obra_id: str,
    body: AtualizarStatusObraBody,
    admin=Depends(require_admin),
):
    obra = aprovacao_service.atualizar_status_obra(
        obra_id=obra_id,
        admin_id=str(admin["_id"]),
        status=body.status.value,
        motivo_rejeicao=body.motivo_rejeicao,
    )
    if not obra:
        raise HTTPException(status_code=404, detail="Obra nÃ£o encontrada")
    return obra


# Lista eventos de auditoria para apoiar monitoramento operacional e administrativo.
@router.get("/eventos", response_model=EventoAuditoriaListResponseSchema)
def listar_eventos(
    alvo_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    admin=Depends(require_admin),
):
    eventos = auditoria_service.listar_eventos(alvo_id=alvo_id, limit=limit)
    return _resposta_paginada(
        EventoAuditoriaListResponseSchema,
        EventoAuditoriaResponse,
        eventos,
    )
