from enum import Enum


class UserStatus(str, Enum):
    PENDENTE = "pendente"
    APROVADO = "aprovado"
    REJEITADO = "rejeitado"
    SUSPENSO = "suspenso"


class ApprovalStatus(str, Enum):
    PENDENTE = "pendente_aprovacao"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"
