from datetime import datetime, timezone

from app.core.database import auditoria_collection


# Devolve o timestamp UTC usado para carimbar eventos de auditoria.
def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


# Registra um evento operacional ou administrativo para rastreabilidade posterior.
def registrar_evento(
    tipo: str,
    ator_id: str | None = None,
    alvo_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    documento = {
        "tipo": tipo,
        "ator_id": ator_id,
        "alvo_id": alvo_id,
        "metadata": metadata or {},
        "criado_em": _agora_utc(),
    }
    resultado = auditoria_collection.insert_one(documento)
    documento["_id"] = resultado.inserted_id
    return documento


# Lista eventos de auditoria com filtro opcional por alvo para painéis administrativos.
def listar_eventos(alvo_id: str | None = None, limit: int = 100) -> list[dict]:
    filtro = {}
    if alvo_id:
        filtro["alvo_id"] = alvo_id

    return list(
        auditoria_collection.find(filtro).sort([("criado_em", -1)]).limit(limit)
    )
