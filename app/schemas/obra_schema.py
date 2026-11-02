from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field

from app.domain.status import ApprovalStatus
from app.schemas.base_schema import MongoSchema, PaginatedResponseSchema


class ObraCreateSchema(MongoSchema):
    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(min_length=1)
    descricao: Optional[str] = Field(default=None, min_length=1)
    autor: Optional[str] = Field(default=None, min_length=1)
    destinatario: Optional[str] = Field(default=None, min_length=1)
    tipo_obra: Optional[str] = Field(default=None, min_length=1)
    data: Optional[str] = Field(default=None, min_length=1)
    local_expedicao: Optional[str] = Field(default=None, min_length=1)
    preco: Optional[float] = Field(default=None, ge=0)
    observacoes: Optional[str] = Field(default=None, min_length=1)
    imagem_ou_digitalizacao: Optional[str] = Field(default=None, min_length=1)
    ano: Optional[int] = None


class ObraUpdateSchema(MongoSchema):
    model_config = ConfigDict(extra="forbid")

    titulo: Optional[str] = Field(default=None, min_length=1)
    descricao: Optional[str] = Field(default=None, min_length=1)
    autor: Optional[str] = Field(default=None, min_length=1)
    destinatario: Optional[str] = Field(default=None, min_length=1)
    tipo_obra: Optional[str] = Field(default=None, min_length=1)
    data: Optional[str] = Field(default=None, min_length=1)
    local_expedicao: Optional[str] = Field(default=None, min_length=1)
    preco: Optional[float] = Field(default=None, ge=0)
    observacoes: Optional[str] = Field(default=None, min_length=1)
    imagem_ou_digitalizacao: Optional[str] = Field(default=None, min_length=1)
    ano: Optional[int] = None


class ObraResponseSchema(MongoSchema):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str = Field(alias="_id")
    titulo: str
    descricao: Optional[str] = None
    autor: Optional[str] = None
    destinatario: Optional[str] = None
    tipo_obra: Optional[str] = None
    data: Optional[str] = None
    local_expedicao: Optional[str] = None
    preco: Optional[float] = None
    observacoes: Optional[str] = None
    imagem_ou_digitalizacao: Optional[str] = None
    ano: Optional[int] = None
    owner_id: str | None = None
    status_aprovacao: ApprovalStatus = ApprovalStatus.PENDENTE
    visivel_publicamente: bool = False
    aprovado_por: str | None = None
    aprovado_em: datetime | None = None
    motivo_rejeicao: str | None = None
    criado_em: datetime
    atualizado_em: datetime


class ObraListResponseSchema(PaginatedResponseSchema[ObraResponseSchema]):
    items: list[ObraResponseSchema]
