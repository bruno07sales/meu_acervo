from pathlib import Path

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.core.database import gridfs_bucket
from app.core.permissions import require_roles
from app.domain.roles import UserRole, is_internal_role
from app.domain.status import ApprovalStatus
from app.schemas.imagem_schema import (
    ImagemListResponseSchema,
    ImagemResponseSchema,
    ImagemUpdateSchema,
    ImagemUploadSchema,
)
from app.schemas.obra_schema import (
    ObraCreateSchema,
    ObraListResponseSchema,
    ObraResponseSchema,
    ObraUpdateSchema,
)
from app.services import imagem_service, obra_service
from app.services.jwt_service import get_current_user

router = APIRouter(prefix="/obras", tags=["obras"])


# Define o status inicial da obra a partir do papel do usuário que a submeteu.
def _status_inicial_obra(usuario: dict) -> tuple[str, bool]:
    if usuario.get("role") == UserRole.ADMIN.value:
        return ApprovalStatus.APROVADA.value, True
    return ApprovalStatus.PENDENTE.value, False


# Garante que apenas o dono ou perfis internos alterem uma obra existente
def _garantir_permissao_na_obra(obra_id: str, usuario: dict) -> dict:
    documento = obra_service.obter_documento_obra(obra_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    if not obra_service.usuario_pode_editar_obra(usuario, documento):
        raise HTTPException(
            status_code=403, detail="Sem permissão para alterar esta obra"
        )
    return documento


# Garante que apenas o dono ou perfis internos alterem uma imagem existente.
def _garantir_permissao_na_imagem(imagem_id: str, usuario: dict) -> dict:
    documento = imagem_service.obter_documento_por_id(imagem_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    obra = obra_service.obter_documento_obra(str(documento["obra_id"]))
    if not obra:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    if not obra_service.usuario_pode_editar_obra(usuario, obra):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para alterar esta imagem",
        )
    return documento


# Cria uma nova obra respeitando propriedade e ciclo de aprovação por perfil.
@router.post("", response_model=ObraResponseSchema)
def criar_obra(
    dados: ObraCreateSchema,
    usuario=Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.ESTUDANTE_ESTAGIARIO,
            UserRole.COLECIONADOR_NEGOCIADOR,
        )
    ),
):
    status_aprovacao, visivel_publicamente = _status_inicial_obra(usuario)
    return obra_service.criar_obra(
        titulo=dados.titulo,
        descricao=dados.descricao,
        autor=dados.autor,
        destinatario=dados.destinatario,
        tipo_obra=dados.tipo_obra,
        data=dados.data,
        local_expedicao=dados.local_expedicao,
        preco=dados.preco,
        observacoes=dados.observacoes,
        imagem_ou_digitalizacao=dados.imagem_ou_digitalizacao,
        ano=dados.ano,
        owner_id=str(usuario["_id"]),
        status_aprovacao=status_aprovacao,
        visivel_publicamente=visivel_publicamente,
    )


# Lista obras respeitando visibilidade pública, propriedade e perfis internos.
@router.get("", response_model=ObraListResponseSchema)
def listar_obras(
    usuario=Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    q: str | None = Query(None),
    autor: str | None = Query(None),
    ano: int | None = Query(None),
):
    role = usuario.get("role")
    if is_internal_role(role):
        return obra_service.listar_obras(
            page=page,
            limit=limit,
            q=q,
            autor=autor,
            ano=ano,
        )

    if role == UserRole.COLECIONADOR_NEGOCIADOR.value:
        return obra_service.listar_obras(
            page=page,
            limit=limit,
            q=q,
            autor=autor,
            ano=ano,
            owner_id=str(usuario["_id"]),
            include_owner_pending=True,
            somente_publicadas=True,
        )

    return obra_service.listar_obras(
        page=page,
        limit=limit,
        q=q,
        autor=autor,
        ano=ano,
        somente_publicadas=True,
    )


# Lista imagens globais com filtros e paginação para usuários autenticados.
@router.get("/imagens", response_model=ImagemListResponseSchema)
def listar_todas_imagens(
    usuario=Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    obra_id: str | None = Query(None),
    storage: str | None = Query(None),
    q: str | None = Query(None),
    ordem_min: int | None = Query(None, ge=0),
    ordem_max: int | None = Query(None, ge=0),
):
    if is_internal_role(usuario.get("role")):
        return imagem_service.listar_imagens(
            page=page,
            limit=limit,
            obra_id=obra_id,
            storage=storage,
            q=q,
            ordem_min=ordem_min,
            ordem_max=ordem_max,
        )

    if obra_id:
        documento = obra_service.obter_documento_obra(obra_id)
        if not documento:
            raise HTTPException(status_code=404, detail="Obra não encontrada")
        if not obra_service.usuario_pode_visualizar_obra(usuario, documento):
            raise HTTPException(
                status_code=403,
                detail="Sem permissão para visualizar as imagens desta obra",
            )
        return imagem_service.listar_imagens(
            page=page,
            limit=limit,
            obra_id=obra_id,
            storage=storage,
            q=q,
            ordem_min=ordem_min,
            ordem_max=ordem_max,
        )

    obra_ids_permitidas = obra_service.listar_ids_obras_visiveis(
        role=usuario.get("role"),
        usuario_id=(
            str(usuario["_id"])
            if usuario.get("role") == UserRole.COLECIONADOR_NEGOCIADOR.value
            else None
        ),
    )
    if not obra_ids_permitidas:
        return imagem_service.listar_imagens_visiveis(
            page=page,
            limit=limit,
            storage=storage,
            q=q,
            ordem_min=ordem_min,
            ordem_max=ordem_max,
            obra_ids_permitidas=[],
        )

    return imagem_service.listar_imagens_visiveis(
        page=page,
        limit=limit,
        storage=storage,
        q=q,
        ordem_min=ordem_min,
        ordem_max=ordem_max,
        obra_ids_permitidas=obra_ids_permitidas,
    )


# Busca uma obra específica e valida se o usuário atual pode visualizá-la.
@router.get("/{obra_id}", response_model=ObraResponseSchema)
def obter_obra(obra_id: str, usuario=Depends(get_current_user)):
    documento = obra_service.obter_documento_obra(obra_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    if not obra_service.usuario_pode_visualizar_obra(usuario, documento):
        raise HTTPException(
            status_code=403, detail="Sem permissão para visualizar esta obra"
        )
    return ObraResponseSchema.from_document(documento)


# Atualiza os dados de uma obra e recoloca em revisão quando necessário.
@router.post("/{obra_id}", response_model=ObraResponseSchema)
def atualizar_obra(
    obra_id: str,
    dados: ObraUpdateSchema,
    usuario=Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.ESTUDANTE_ESTAGIARIO,
            UserRole.COLECIONADOR_NEGOCIADOR,
        )
    ),
):
    _garantir_permissao_na_obra(obra_id, usuario)
    status_aprovacao = obra_service.UNSET
    visivel_publicamente = obra_service.UNSET
    aprovado_por = obra_service.UNSET
    aprovado_em = obra_service.UNSET
    motivo_rejeicao = obra_service.UNSET

    if usuario.get("role") != UserRole.ADMIN.value:
        status_aprovacao = ApprovalStatus.PENDENTE
        visivel_publicamente = False
        aprovado_por = None
        aprovado_em = None
        motivo_rejeicao = None

    obra = obra_service.atualizar_obra(
        obra_id,
        titulo=dados.titulo,
        descricao=dados.descricao,
        autor=dados.autor,
        destinatario=dados.destinatario,
        tipo_obra=dados.tipo_obra,
        data=dados.data,
        local_expedicao=dados.local_expedicao,
        preco=dados.preco,
        observacoes=dados.observacoes,
        imagem_ou_digitalizacao=dados.imagem_ou_digitalizacao,
        ano=dados.ano,
        status_aprovacao=status_aprovacao,
        visivel_publicamente=visivel_publicamente,
        aprovado_por=aprovado_por,
        aprovado_em=aprovado_em,
        motivo_rejeicao=motivo_rejeicao,
    )
    if not obra:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    return obra


# Exclui uma obra e seus dados associados respeitando o controle de propriedade.
@router.delete("/{obra_id}")
def excluir_obra(
    obra_id: str,
    usuario=Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.ESTUDANTE_ESTAGIARIO,
            UserRole.COLECIONADOR_NEGOCIADOR,
        )
    ),
):
    _garantir_permissao_na_obra(obra_id, usuario)
    if not obra_service.excluir_obra(obra_id):
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    return {"message": "Obra excluída"}


# Cadastra uma nova imagem vinculada a uma obra já autorizada para edição.
@router.post("/{obra_id}/imagens", response_model=ImagemResponseSchema)
def cadastrar_imagem(
    obra_id: str,
    arquivo: UploadFile = File(...),
    dados: ImagemUploadSchema = Depends(ImagemUploadSchema.as_form),
    usuario=Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.ESTUDANTE_ESTAGIARIO,
            UserRole.COLECIONADOR_NEGOCIADOR,
        )
    ),
):
    _garantir_permissao_na_obra(obra_id, usuario)
    return imagem_service.salvar(
        obra_id,
        arquivo,
        descricao=dados.descricao,
        ordem=dados.ordem,
    )


# Lista as imagens associadas a uma obra que o usuário atual pode visualizar.
@router.get("/{obra_id}/imagens", response_model=ImagemListResponseSchema)
def listar_imagens(
    obra_id: str,
    usuario=Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    storage: str | None = Query(None),
    q: str | None = Query(None),
    ordem_min: int | None = Query(None, ge=0),
    ordem_max: int | None = Query(None, ge=0),
):
    documento = obra_service.obter_documento_obra(obra_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    if not obra_service.usuario_pode_visualizar_obra(usuario, documento):
        raise HTTPException(
            status_code=403, detail="Sem permissão para visualizar esta obra"
        )

    return imagem_service.listar_imagens(
        page=page,
        limit=limit,
        obra_id=obra_id,
        storage=storage,
        q=q,
        ordem_min=ordem_min,
        ordem_max=ordem_max,
    )


# Retorna o binário de uma imagem armazenada localmente ou no GridFS.
@router.get("/imagens/{imagem_id}")
def obter_imagem(imagem_id: str, usuario=Depends(get_current_user)):
    documento = imagem_service.obter_documento_por_id(imagem_id)
    if not documento:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")

    obra = obra_service.obter_documento_obra(str(documento["obra_id"]))
    if not obra:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    if not obra_service.usuario_pode_visualizar_obra(usuario, obra):
        raise HTTPException(
            status_code=403,
            detail="Sem permissão para visualizar esta imagem",
        )

    imagem = ImagemResponseSchema.from_document(documento)

    if imagem.storage == "local":
        caminho = Path(imagem.arquivo_local)
        return FileResponse(
            path=caminho,
            media_type=imagem.content_type or "application/octet-stream",
            filename=imagem.nome_original or caminho.name,
        )

    if imagem.storage == "gridfs":
        arquivo_id = imagem.arquivo_gridfs_id
        try:
            grid_out = gridfs_bucket.get(ObjectId(str(arquivo_id)))
        except (InvalidId, TypeError):
            raise HTTPException(status_code=400, detail="ID de arquivo inválido")

        # Gera os pedaços do arquivo para streaming da resposta.
        def iter_chunks(chunk_size: int = 8192):
            while True:
                chunk = grid_out.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        return StreamingResponse(
            iter_chunks(),
            media_type=imagem.content_type or "application/octet-stream",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{imagem.nome_original or "arquivo"}"'
                )
            },
        )

    raise HTTPException(status_code=400, detail="Tipo de armazenamento inválido")


# Atualiza metadados ou arquivo de uma imagem respeitando a permissão sobre a obra.
@router.post("/imagens/{imagem_id}", response_model=ImagemResponseSchema)
def atualizar_imagem(
    imagem_id: str,
    arquivo: UploadFile | None = File(None),
    dados: ImagemUpdateSchema = Depends(ImagemUpdateSchema.as_form),
    usuario=Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.ESTUDANTE_ESTAGIARIO,
            UserRole.COLECIONADOR_NEGOCIADOR,
        )
    ),
):
    _garantir_permissao_na_imagem(imagem_id, usuario)
    imagem = imagem_service.atualizar_imagem(
        imagem_id,
        arquivo=arquivo,
        descricao=dados.descricao,
        ordem=dados.ordem,
    )
    if not imagem:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    return imagem


# Remove uma imagem cadastrada e seu arquivo associado respeitando a obra de origem.
@router.delete("/imagens/{imagem_id}")
def excluir_imagem(
    imagem_id: str,
    usuario=Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.ESTUDANTE_ESTAGIARIO,
            UserRole.COLECIONADOR_NEGOCIADOR,
        )
    ),
):
    _garantir_permissao_na_imagem(imagem_id, usuario)
    if not imagem_service.excluir_imagem(imagem_id):
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    return {"message": "Imagem excluída"}
