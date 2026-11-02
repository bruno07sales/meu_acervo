from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.roles import UserRole, is_admin_managed_role
from app.domain.status import UserStatus
from app.schemas.base_schema import MongoSchema


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    senha: str = Field(min_length=6)


class UsuarioCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    senha: str = Field(min_length=6)
    nome: str | None = Field(default=None, min_length=1)


class UsuarioCreateResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    message: str
    role: UserRole
    status: UserStatus


class UsuarioAdminCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    senha: str = Field(min_length=6)
    nome: str | None = Field(default=None, min_length=1)
    role: UserRole

    @field_validator("role")
    @classmethod
    # Restringe a criação administrativa aos perfis internos previstos no negócio.
    def validar_role_admin(cls, value: UserRole) -> UserRole:
        if not is_admin_managed_role(value):
            raise ValueError("role inválida para criação administrativa")
        return value


class UsuarioMonitoramentoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    monitorar: bool = True


class UsuarioStatusResponse(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    message: str
    status: Literal["ativo", "removido"]


class UsuarioResponseSchema(MongoSchema):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    id: str = Field(alias="_id")
    email: EmailStr
    nome: str | None = None
    role: UserRole
    status: UserStatus = UserStatus.APROVADO
    ativo: bool = True
    aprovado_por: str | None = None
    aprovado_em: datetime | None = None
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None
    perfil_monitorado_ids: list[str] = Field(default_factory=list)
