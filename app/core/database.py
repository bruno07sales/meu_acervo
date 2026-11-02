from pymongo.mongo_client import MongoClient
from gridfs import GridFS

from app.core.config import settings


client = MongoClient(settings.MONGO_URI)


db = client[settings.MONGO_DB_NAME]
collection = db["usuarios"]
usuarios_collection = db["usuarios"]
obras_collection = db["obras"]
imagens_collection = db["imagens"]
auditoria_collection = db["auditoria"]
gridfs_bucket = GridFS(db)
