from datetime import datetime

from pydantic import Field

from app.schemas.base_schema import MongoSchema, PaginatedResponseSchema


class EventoAuditoriaResponse(MongoSchema):
    id: str = Field(alias="_id")
    tipo: str
    ator_id: str | None = None
    alvo_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    criado_em: datetime


class EventoAuditoriaListResponseSchema(PaginatedResponseSchema[EventoAuditoriaResponse]):
    items: list[EventoAuditoriaResponse]
