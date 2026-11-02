from fastapi import Depends, HTTPException

from app.domain.roles import UserRole
from app.domain.status import UserStatus
from app.services.jwt_service import get_current_user


# Normaliza papéis recebidos como enum ou texto para reutilizar nas validações.
def _role_value(role: str | UserRole) -> str:
    return role.value if isinstance(role, UserRole) else str(role)


# Garante que o usuário autenticado pertença a um dos papéis exigidos pela rota.
def require_roles(*roles: str | UserRole):
    allowed_roles = {_role_value(role) for role in roles}

    # Aplica a validação de papéis após a autenticação principal da sessão.
    def dependency(usuario=Depends(get_current_user)):
        if usuario.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Sem permissão para esta ação")
        return usuario

    return dependency


# Garante que o usuário autenticado esteja em um dos estados de acesso aceitos.
def require_status(*statuses: str | UserStatus):
    allowed_statuses = {
        status.value if isinstance(status, UserStatus) else str(status)
        for status in statuses
    }

    # Aplica a validação de status para reaproveitar a mesma lógica em várias rotas.
    def dependency(usuario=Depends(get_current_user)):
        status_atual = usuario.get("status", UserStatus.APROVADO.value)
        if status_atual not in allowed_statuses:
            raise HTTPException(status_code=403, detail="Usuário sem liberação de acesso")
        return usuario

    return dependency


# Atalho para rotas estritamente administrativas.
def require_admin(usuario=Depends(require_roles(UserRole.ADMIN))):
    return usuario
