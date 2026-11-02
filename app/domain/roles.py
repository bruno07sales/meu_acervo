from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    ESTUDANTE_ESTAGIARIO = "estudante_estagiario"
    COLECIONADOR_NEGOCIADOR = "colecionador_negociador"
    LOCATARIO = "locatario"


# Indica quais papéis representam operação interna com visibilidade ampliada.
def is_internal_role(role: str | UserRole) -> bool:
    valor = role.value if isinstance(role, UserRole) else str(role)
    return valor in {UserRole.ADMIN.value, UserRole.ESTUDANTE_ESTAGIARIO.value}


# Indica quais papéis podem ser criados diretamente por um administrador.
def is_admin_managed_role(role: str | UserRole) -> bool:
    valor = role.value if isinstance(role, UserRole) else str(role)
    return valor in {
        UserRole.ESTUDANTE_ESTAGIARIO.value,
        UserRole.COLECIONADOR_NEGOCIADOR.value,
    }
