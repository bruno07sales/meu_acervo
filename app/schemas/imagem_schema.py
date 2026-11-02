from datetime import datetime
from typing import Optional

from fastapi import Form
from pydantic import ConfigDict, Field

from app.schemas.base_schema import MongoSchema, PaginatedResponseSchema


class ImagemUploadSchema(MongoSchema):
    model_config = ConfigDict(extra="forbid")

    descricao: Optional[str] = Field(default=None, min_length=1)
    ordem: int = Field(default=0, ge=0)

    @classmethod
    def as_form(
        cls,
        descricao: Optional[str] = Form(None),
        ordem: int = Form(0),
    ) -> "ImagemUploadSchema":
        return cls(descricao=descricao, ordem=ordem)


class ImagemUpdateSchema(MongoSchema):
    model_config = ConfigDict(extra="forbid")

    descricao: Optional[str] = Field(default=None, min_length=1)
    ordem: Optional[int] = Field(default=None, ge=0)

    @classmethod
    def as_form(
        cls,
        descricao: Optional[str] = Form(None),
        ordem: Optional[int] = Form(None),
    ) -> "ImagemUpdateSchema":
        return cls(descricao=descricao, ordem=ordem)


class ImagemResponseSchema(MongoSchema):
    id: str = Field(alias="_id")
    obra_id: str
    descricao: Optional[str] = None
    ordem: int
    nome_original: str
    content_type: Optional[str] = None
    storage: str
    criado_em: datetime
    atualizado_em: datetime
    url: Optional[str] = None
    arquivo_local: Optional[str] = None
    arquivo_gridfs_id: Optional[str] = None

class ImagemListResponseSchema(PaginatedResponseSchema[ImagemResponseSchema]):
    items: list[ImagemResponseSchema]
