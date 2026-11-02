from typing import Any, Generic, Iterable, TypeVar

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator


SchemaT = TypeVar("SchemaT", bound="MongoSchema")
ItemSchemaT = TypeVar("ItemSchemaT", bound="MongoSchema")


class MongoSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    @field_validator("*", mode="before")
    @classmethod
    def serializar_ids_mongo(cls, valor: Any, info: ValidationInfo) -> Any:
        field_name = info.field_name or ""
        if valor is None:
            return None
        if isinstance(valor, ObjectId):
            return str(valor)
        if isinstance(valor, list):
            return [str(item) if isinstance(item, ObjectId) else item for item in valor]
        if field_name == "id" or field_name.endswith("_id"):
            return str(valor)
        return valor

    @classmethod
    def from_document(cls: type[SchemaT], document: dict[str, Any]) -> SchemaT:
        return cls.model_validate(document)

    @classmethod
    def from_documents(
        cls: type[SchemaT],
        documents: Iterable[dict[str, Any]],
    ) -> list[SchemaT]:
        return [cls.from_document(document) for document in documents]


class PaginationSchema(BaseModel):
    page: int
    limit: int
    total: int
    pages: int

    @classmethod
    def from_total(cls, *, page: int, limit: int, total: int) -> "PaginationSchema":
        return cls(
            page=page,
            limit=limit,
            total=total,
            pages=(total + limit - 1) // limit if total else 0,
        )


class PaginatedResponseSchema(BaseModel, Generic[ItemSchemaT]):
    items: list[ItemSchemaT]
    pagination: PaginationSchema

    @classmethod
    def from_documents(
        cls,
        *,
        item_schema: type[ItemSchemaT],
        documents: Iterable[dict[str, Any]],
        page: int,
        limit: int,
        total: int,
    ):
        return cls(
            items=item_schema.from_documents(documents),
            pagination=PaginationSchema.from_total(page=page, limit=limit, total=total),
        )
