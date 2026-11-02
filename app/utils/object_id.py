from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException


# Converte uma string em ObjectId ou dispara erro HTTP valido.
def object_id(valor: str) -> ObjectId:
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="ID invalido")
