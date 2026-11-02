from app.schemas.base_schema import PaginatedResponseSchema
from app.schemas.usuario_schema import UsuarioResponseSchema


class UsuarioListResponseSchema(PaginatedResponseSchema[UsuarioResponseSchema]):
    items: list[UsuarioResponseSchema]
