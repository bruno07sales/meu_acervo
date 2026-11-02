from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.routers.admin_router import router as admin_router
from app.routers.auth_router import router as auth_router
from app.routers.obra_router import router as obra_router
from app.services.auth_service import garantir_admin_bootstrap


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(
    title="Art.me API",
    summary="API para gerenciamento de obras de arte, autenticação de usuários e administração do sistema.",
    # Curiosidade: description aceita markdown.
    description="A vida é muito curta para se resumir a código... viva a arte! Art.me",
    version="1.0.4",
    # redocs_url=None,  # Desabilitei a documentação automatica do Redoc, só pra treinar mesmo",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.all_cors_origins,
    allow_origin_regex=settings.local_cors_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.on_event("startup")
# Inicializa recursos obrigatorios quando a aplição sobe.
def startup_event():
    garantir_admin_bootstrap()


@app.get("/", include_in_schema=False)
# Serve o frontend principal quando o arquivo index existe.
def frontend_home():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return {"detail": "Frontend nao encontrado"}
    return FileResponse(index_file)


app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(obra_router, prefix=settings.API_V1_STR)
