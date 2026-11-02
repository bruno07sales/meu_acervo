from typing import Literal
from app.services import auditoria_service, obra_service, usuario_service


# Aprova ou rejeita um usuário pendente em uma única operação administrativa.
def atualizar_status_usuario(
    usuario_id: str,
    admin_id: str,
    status: Literal["aprovado", "rejeitado"],
) -> dict | None:
    usuario = usuario_service.atualizar_status_usuario(
        usuario_id,
        status=status,
        aprovado_por=admin_id,
    )
    if usuario:
        auditoria_service.registrar_evento(
            f"usuario_{status}",
            ator_id=admin_id,
            alvo_id=usuario_id,
            metadata={"status": status},
        )
    return usuario


# Lista usuários que aguardam decisão administrativa.
def listar_usuarios_pendentes() -> list[dict]:
    return usuario_service.listar_usuarios_pendentes()


# Lista todos os usuários para gestão administrativa ampla.
def listar_usuarios() -> list[dict]:
    return usuario_service.listar_usuarios()


# Aprova ou rejeita uma obra submetida para revisão em uma única operação administrativa.
def atualizar_status_obra(
    obra_id: str,
    admin_id: str,
    status: Literal["aprovada", "rejeitada"],
    motivo_rejeicao: str | None = None,
):
    if status == "aprovada":
        obra = obra_service.aprovar_obra(obra_id, admin_id)
    else:
        obra = obra_service.rejeitar_obra(obra_id, admin_id, motivo_rejeicao)

    if obra:
        auditoria_service.registrar_evento(
            f"obra_{status}",
            ator_id=admin_id,
            alvo_id=obra_id,
            metadata={
                "status_aprovacao": status,
                "motivo_rejeicao": motivo_rejeicao,
            },
        )
    return obra


# Lista obras que ainda aguardam revisão por um administrador.
def listar_obras_pendentes():
    return obra_service.listar_obras_pendentes()


# Lista obras legadas que ainda dependem de migração ou revisão administrativa.
def listar_obras_legadas():
    return obra_service.listar_obras_legadas()
