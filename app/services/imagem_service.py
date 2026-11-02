import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, UploadFile
from pymongo import ReturnDocument

from app.core.config import settings
from app.core.database import gridfs_bucket, imagens_collection, obras_collection
from app.domain.status import ApprovalStatus
from app.schemas.imagem_schema import ImagemListResponseSchema, ImagemResponseSchema


UPLOAD_ROOT = Path("uploads") / "obras"


# Converte o identificador recebido para ObjectId e padroniza o erro HTTP de imagem invalida para ser usado em varios pontos do service
def _object_id(valor: str) -> ObjectId:
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="ID de imagem invalido")


# Busca o documento bruto da imagem para permitir checagens de autorização antes de editar ou excluir.
def obter_documento_por_id(imagem_id: str) -> dict | None:
    return imagens_collection.find_one({"_id": _object_id(imagem_id)})


# Normaliza o id da obra como texto canônico de ObjectId para manter o mesmo formato no banco e evitar erros de comparação ou vinculação entre os arquivos e as obras
def _normalizar_obra_id(obra_id: str) -> str:
    try:
        return str(ObjectId(obra_id))
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="ID de obra invalido")


# Garante que a obra existe antes de vincular arquivos a ela, para evitar arquivos órfãos e manter a integridade referencial entre as coleções de obras e imagens
def _garantir_obra_existe(obra_id: str) -> str:
    obra_id_normalizado = _normalizar_obra_id(obra_id)
    obra = obras_collection.find_one({"_id": ObjectId(obra_id_normalizado)})
    if not obra:
        raise HTTPException(status_code=404, detail="Obra não encontrada")
    return obra_id_normalizado


# Monta os metadados comuns usados pelos dois fluxos no backends(salvamento local e GridFS) para garantir consistencia e evitar repetição de código entre as estratégias de armazenamento
def _base_documento(
    obra_id: str,
    arquivo: UploadFile,
    descricao: str | None,
    ordem: int | None,
    storage: str,
) -> dict:
    agora = datetime.now(timezone.utc)
    return {
        "obra_id": obra_id,
        "descricao": descricao,
        "ordem": ordem if ordem is not None else 0,
        "nome_original": arquivo.filename,
        "content_type": getattr(arquivo, "content_type", None),
        "storage": storage,
        "criado_em": agora,
        "atualizado_em": agora,
    }


# Salva o binário no disco local com nome único e devolve a URL publica
def _salvar_local_no_disco(obra_id: str, arquivo: UploadFile) -> tuple[str, Path]:
    obra_dir = UPLOAD_ROOT / obra_id
    obra_dir.mkdir(parents=True, exist_ok=True)

    extensao = Path(arquivo.filename or "").suffix
    nome_arquivo = f"{uuid4().hex}{extensao}"
    destino = obra_dir / nome_arquivo

    with destino.open("wb") as buffer:
        shutil.copyfileobj(arquivo.file, buffer)

    return f"/uploads/obras/{obra_id}/{nome_arquivo}", destino


# Prepara os campos persistidos quando o backend de imagem eh local, incluindo a URL de acesso e o caminho do arquivo no disco para futuras operações de leitura ou exclusão
def _armazenar_novo_arquivo_local(obra_id: str, arquivo: UploadFile) -> dict:
    url, destino = _salvar_local_no_disco(obra_id, arquivo)
    return {
        "url": url,
        "arquivo_local": str(destino),
        "nome_original": arquivo.filename,
        "content_type": getattr(arquivo, "content_type", None),
    }


# Envia o arquivo para o GridFS e devolve os metadados necessários para persistência
def _armazenar_novo_arquivo_gridfs(obra_id: str, arquivo: UploadFile) -> dict:
    arquivo_id = gridfs_bucket.put(
        arquivo.file,
        filename=arquivo.filename,
        content_type=getattr(arquivo, "content_type", None),
        obra_id=obra_id,
    )
    return {
        "arquivo_gridfs_id": arquivo_id,
        "nome_original": arquivo.filename,
        "content_type": getattr(arquivo, "content_type", None),
    }


# Salva uma imagem usando armazenamento local e persiste seus metadados no MongoDB
def salvar_local(
    obra_id: str,
    arquivo: UploadFile,
    descricao: str | None = None,
    ordem: int | None = 0,
) -> ImagemResponseSchema:
    if not arquivo.filename:
        raise HTTPException(status_code=400, detail="Arquivo invalido")

    obra_id_normalizado = _garantir_obra_existe(obra_id)
    documento = _base_documento(obra_id_normalizado, arquivo, descricao, ordem, "local")
    documento.update(_armazenar_novo_arquivo_local(obra_id_normalizado, arquivo))
    resultado = imagens_collection.insert_one(documento)
    documento["_id"] = resultado.inserted_id
    return ImagemResponseSchema.from_document(documento)


# Salva uma imagem no GridFS e persiste a referência do arquivo no MongoDB
def salvar_gridfs(
    obra_id: str,
    arquivo: UploadFile,
    descricao: str | None = None,
    ordem: int | None = 0,
) -> ImagemResponseSchema:
    if not arquivo.filename:
        raise HTTPException(status_code=400, detail="Arquivo invalido")

    obra_id_normalizado = _garantir_obra_existe(obra_id)
    documento = _base_documento(
        obra_id_normalizado, arquivo, descricao, ordem, "gridfs"
    )
    documento.update(_armazenar_novo_arquivo_gridfs(obra_id_normalizado, arquivo))
    resultado = imagens_collection.insert_one(documento)
    documento["_id"] = resultado.inserted_id
    return ImagemResponseSchema.from_document(documento)


# Escolhe o backend configurado e delega o salvamento para a estratégia correta
def salvar(
    obra_id: str,
    arquivo: UploadFile,
    descricao: str | None = None,
    ordem: int | None = 0,
) -> ImagemResponseSchema:
    backend = (settings.IMAGEM_STORAGE_BACKEND or "local").lower()
    if backend == "gridfs":
        return salvar_gridfs(obra_id, arquivo, descricao, ordem)
    return salvar_local(obra_id, arquivo, descricao, ordem)


# Busca uma imagem pelo id e converte o documento do banco em schema de resposta
def obter_por_id(imagem_id: str) -> ImagemResponseSchema | None:
    documento = obter_documento_por_id(imagem_id)
    if not documento:
        return None
    return ImagemResponseSchema.from_document(documento)


# Lista todas as imagens de uma obra ordenando pela sequência esperada de exibição, e convertendo os documentos do banco em schemas de resposta para a API
def listar_por_obra(obra_id: str) -> list[ImagemResponseSchema]:
    obra_id_normalizado = _normalizar_obra_id(obra_id)
    imagens = imagens_collection.find({"obra_id": obra_id_normalizado}).sort(
        [("ordem", 1), ("criado_em", 1)]
    )
    return ImagemResponseSchema.from_documents(imagens)


# Lista imagens com filtros e paginação para uso geral ou por obra
def listar_imagens(
    page: int = 1,
    limit: int = 10,
    obra_id: str | None = None,
    storage: str | None = None,
    q: str | None = None,
    ordem_min: int | None = None,
    ordem_max: int | None = None,
    obra_ids: list[str] | None = None,
) -> ImagemListResponseSchema:
    filtro: dict = {}
    if obra_id:
        filtro["obra_id"] = _normalizar_obra_id(obra_id)
    elif obra_ids is not None:
        filtro["obra_id"] = {"$in": obra_ids}
    if storage:
        filtro["storage"] = storage
    if q:
        regex = {"$regex": q, "$options": "i"}
        filtro["$or"] = [
            {"descricao": regex},
            {"nome_original": regex},
        ]
    if ordem_min is not None or ordem_max is not None:
        filtro["ordem"] = {}
        if ordem_min is not None:
            filtro["ordem"]["$gte"] = ordem_min
        if ordem_max is not None:
            filtro["ordem"]["$lte"] = ordem_max
        if not filtro["ordem"]:
            filtro.pop("ordem", None)
    # TODO: diminuir esse tanto de If's e pensar em abordagem mais dinâmica para construção de filtros, talvez usando uma função utilitária que mapeia os parâmetros de consulta para operadores do MongoDB de forma mais genérica e escalável, evitando a necessidade de muitos blocos condicionais específicos para cada campo ou tipo de filtro (ainda vou entender como fazer)
    page = max(page, 1)
    limit = max(limit, 1)
    skip = (page - 1) * limit
    total = imagens_collection.count_documents(filtro)
    cursor = (
        imagens_collection.find(filtro)
        .sort([("ordem", 1), ("criado_em", -1)])
        .skip(skip)
        .limit(limit)
    )
    return ImagemListResponseSchema.from_documents(
        item_schema=ImagemResponseSchema,
        documents=cursor,
        page=page,
        limit=limit,
        total=total,
    )


# Lista imagens vinculadas apenas a obras publicadas ou a obras explicitamente permitidas para o usuário atual.
def listar_imagens_visiveis(
    page: int = 1,
    limit: int = 10,
    obra_id: str | None = None,
    storage: str | None = None,
    q: str | None = None,
    ordem_min: int | None = None,
    ordem_max: int | None = None,
    obra_ids_permitidas: list[str] | None = None,
) -> ImagemListResponseSchema:
    obra_ids_filtradas = obra_ids_permitidas if obra_id is None else None
    return listar_imagens(
        page=page,
        limit=limit,
        obra_id=obra_id,
        storage=storage,
        q=q,
        ordem_min=ordem_min,
        ordem_max=ordem_max,
        obra_ids=obra_ids_filtradas,
    )


# Atualiza metadados e, quando necessário, substitui o arquivo limpando o recurso antigo com segurança
def atualizar_imagem(
    imagem_id: str,
    arquivo: UploadFile | None = None,
    descricao: str | None = None,
    ordem: int | None = None,
) -> ImagemResponseSchema | None:
    documento_atual = imagens_collection.find_one({"_id": _object_id(imagem_id)})
    if not documento_atual:
        return None

    atualizacoes = {
        chave: valor
        for chave, valor in {
            "descricao": descricao,
            "ordem": ordem,
        }.items()
        if valor is not None
    }

    arquivo_local_antigo = None
    arquivo_gridfs_antigo = None
    novo_arquivo_gridfs_id = None
    novo_arquivo_local = None

    if arquivo is not None and arquivo.filename:
        if documento_atual.get("storage") == "local":
            novo_arquivo_local = _armazenar_novo_arquivo_local(
                documento_atual["obra_id"], arquivo
            )
            atualizacoes.update(novo_arquivo_local)
            arquivo_local_antigo = documento_atual.get("arquivo_local")
        elif documento_atual.get("storage") == "gridfs":
            novo_arquivo_gridfs = _armazenar_novo_arquivo_gridfs(
                documento_atual["obra_id"], arquivo
            )
            atualizacoes.update(novo_arquivo_gridfs)
            novo_arquivo_gridfs_id = novo_arquivo_gridfs["arquivo_gridfs_id"]
            arquivo_gridfs_antigo = documento_atual.get("arquivo_gridfs_id")

    if not atualizacoes:
        return ImagemResponseSchema.from_document(documento_atual)

    atualizacoes["atualizado_em"] = datetime.now(timezone.utc)

    try:
        documento = imagens_collection.find_one_and_update(
            {"_id": _object_id(imagem_id)},
            {"$set": atualizacoes},
            return_document=ReturnDocument.AFTER,
        )
    except Exception:
        if novo_arquivo_local is not None:
            Path(novo_arquivo_local["arquivo_local"]).unlink(missing_ok=True)
        if novo_arquivo_gridfs_id is not None:
            gridfs_bucket.delete(ObjectId(str(novo_arquivo_gridfs_id)))
        raise

    if not documento:
        if novo_arquivo_local is not None:
            Path(novo_arquivo_local["arquivo_local"]).unlink(missing_ok=True)
        if novo_arquivo_gridfs_id is not None:
            gridfs_bucket.delete(ObjectId(str(novo_arquivo_gridfs_id)))
        return None

    if arquivo_local_antigo:
        Path(arquivo_local_antigo).unlink(missing_ok=True)
    if arquivo_gridfs_antigo is not None:
        gridfs_bucket.delete(ObjectId(str(arquivo_gridfs_antigo)))

    return ImagemResponseSchema.from_document(documento)


# TODO: pensar me como diminuir os if´s (poderia usar utilitario de mapeamento de campos?)
# TODO: implementar função utilitária para mapear parâmetros de consulta para operadores do MongoDB


# Remove a imagem e apaga tambem o arquivo fisico ou o binário salvo no GridFS
def excluir_imagem(imagem_id: str) -> bool:
    documento = obter_documento_por_id(imagem_id)
    if not documento:
        return False

    if documento.get("storage") == "local":
        arquivo_local = documento.get("arquivo_local")
        if arquivo_local:
            Path(arquivo_local).unlink(missing_ok=True)
    elif documento.get("storage") == "gridfs":
        arquivo_gridfs_id = documento.get("arquivo_gridfs_id")
        if arquivo_gridfs_id is not None:
            gridfs_bucket.delete(ObjectId(str(arquivo_gridfs_id)))

    resultado = imagens_collection.delete_one({"_id": _object_id(imagem_id)})
    return resultado.deleted_count > 0


# Exclui em lote todas as imagens de uma obra de arte, incluindo os arquivos associados
def remover_por_obra(obra_id: str) -> int:
    obra_id_normalizado = _normalizar_obra_id(obra_id)
    imagens = list(imagens_collection.find({"obra_id": obra_id_normalizado}))
    for imagem in imagens:
        if imagem.get("storage") == "local":
            arquivo_local = imagem.get("arquivo_local")
            if arquivo_local:
                Path(arquivo_local).unlink(missing_ok=True)
        elif imagem.get("storage") == "gridfs":
            arquivo_gridfs_id = imagem.get("arquivo_gridfs_id")
            if arquivo_gridfs_id is not None:
                gridfs_bucket.delete(ObjectId(str(arquivo_gridfs_id)))

    resultado = imagens_collection.delete_many({"obra_id": obra_id_normalizado})
    return resultado.deleted_count
