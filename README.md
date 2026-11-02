# ArtMe Backend

API REST do ArtMe para catalogação de obras de arte, gerenciamento de imagens e controle de usuários. A aplicação usa FastAPI e MongoDB, autenticação JWT em cookie e um fluxo de aprovação administrativa para usuários e obras.

## Recursos

- autenticação por cookie HTTP-only;
- pré-cadastro público de locatários;
- usuários com papéis e permissões diferentes;
- cadastro, consulta, atualização e exclusão de obras;
- aprovação administrativa de usuários e obras;
- upload de imagens em disco local ou no GridFS;
- paginação e filtros para obras e imagens;
- registro de eventos de auditoria;
- documentação interativa gerada pelo FastAPI.

## Tecnologias

- Python 3.13
- FastAPI
- Pydantic
- MongoDB, PyMongo e GridFS
- JWT (`python-jose`)
- Uvicorn
- Docker

## Pré-requisitos

- Python 3.13 ou Docker;
- uma instância do MongoDB acessível pela aplicação.

## Configuração

Crie um arquivo `.env` na raiz do projeto. As opções disponíveis são:

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `API_V1_STR` | `/api/v1` | Prefixo das rotas da API |
| `APP_NAME` | `artme-backend` | Nome da aplicação |
| `ENV` | `development` | Ambiente: `development` ou `production` |
| `CORS_ORIGINS` | `http://localhost:3000` | Origens permitidas, separadas por vírgula |
| `SECRET_KEY` | `change-me-in-production` | Chave usada para assinar os JWTs |
| `MONGO_URI` | `mongodb://127.0.0.1:27017` | URI de conexão com o MongoDB |
| `MONGO_DB_NAME` | `artme` | Nome do banco de dados |
| `IMAGEM_STORAGE_BACKEND` | `local` | Armazenamento de imagens: `local` ou `gridfs` |
| `JWT_EXP_SECONDS` | `3600` | Validade do token, em segundos |
| `COOKIE_NAME` | `access_token` | Nome do cookie de autenticação |
| `COOKIE_MAX_AGE` | `3600` | Validade do cookie, em segundos |
| `COOKIE_SECURE` | `false` | Envia o cookie apenas por HTTPS |
| `COOKIE_SAMESITE` | `lax` | Política SameSite: `lax`, `strict` ou `none` |
| `COOKIE_PATH` | `/` | Escopo de caminho do cookie |
| `ENABLE_BOOTSTRAP_ADMIN` | `false` | Cria o administrador inicial na inicialização |
| `BOOTSTRAP_ADMIN_EMAIL` | — | E-mail do administrador inicial |
| `BOOTSTRAP_ADMIN_PASSWORD` | — | Senha do administrador inicial |
| `BOOTSTRAP_ADMIN_NAME` | `Administrador inicial` | Nome do administrador inicial |

Exemplo para desenvolvimento:

```env
ENV=development
SECRET_KEY=troque-por-uma-chave-segura
MONGO_URI=mongodb://127.0.0.1:27017
MONGO_DB_NAME=artme
CORS_ORIGINS=http://localhost:3000
IMAGEM_STORAGE_BACKEND=local

ENABLE_BOOTSTRAP_ADMIN=true
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
BOOTSTRAP_ADMIN_PASSWORD=uma-senha-segura
```

Em produção, defina uma `SECRET_KEY` forte, habilite `COOKIE_SECURE=true` e configure explicitamente as origens permitidas.

## Execução local

Crie e ative um ambiente virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale as dependências e inicie a API:

```powershell
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

A aplicação ficará disponível em `http://localhost:8000`. A documentação interativa pode ser acessada em:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Docker

```bash
docker build -t artme-backend .
docker run --rm -p 8000:8000 --env-file .env artme-backend
```

O MongoDB precisa estar acessível de dentro do contêiner. Se ele estiver sendo executado na máquina host, ajuste `MONGO_URI` conforme o ambiente (por exemplo, usando `host.docker.internal` no Docker Desktop).

## Papéis e permissões

| Papel | Forma de cadastro | Acesso principal |
| --- | --- | --- |
| `admin` | Bootstrap administrativo | Acesso total, aprovação, monitoramento e auditoria |
| `estudante_estagiario` | Criado por administrador | Cria e edita obras |
| `colecionador_negociador` | Criado por administrador | Cria obras e edita apenas as próprias |
| `locatario` | Pré-cadastro público | Consulta após aprovação; não cria nem edita obras |

Os estados possíveis de um usuário são `pendente`, `aprovado`, `rejeitado` e `suspenso`.

### Aprovação de obras

- Obras criadas por administradores entram como `aprovada` e ficam visíveis publicamente.
- Obras criadas por estudantes ou colecionadores entram como `pendente_aprovacao` e não ficam visíveis publicamente.
- A edição de uma obra por um usuário não administrador a devolve ao fluxo de aprovação.
- Um administrador aprova ou rejeita a obra pela rota `POST /api/v1/admin/obras/{obra_id}/status`.

## Catalogação de obras

O campo `titulo` é obrigatório. Os demais dados de catalogação são opcionais:

- `descricao`, `autor`, `destinatario` e `tipo_obra`;
- `data`, `ano` e `local_expedicao`;
- `preco` e `observacoes`;
- `imagem_ou_digitalizacao`.

O campo `imagem_ou_digitalizacao` é um metadado textual. Arquivos são enviados separadamente pelas rotas de imagens, usando `multipart/form-data`.

## Endpoints

Todas as rotas abaixo usam o prefixo padrão `/api/v1`.

### Autenticação

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/auth/pre-cadastro-locatario` | Cria um locatário pendente de aprovação |
| `POST` | `/auth/login` | Autentica e grava o JWT no cookie |
| `POST` | `/auth/logout` | Remove o cookie de autenticação |

### Administração

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/admin/usuarios` | Cria um usuário interno |
| `GET` | `/admin/usuarios` | Lista usuários |
| `GET` | `/admin/usuarios/pendentes` | Lista usuários pendentes |
| `POST` | `/admin/usuarios/{usuario_id}/status` | Atualiza o estado de um usuário |
| `POST` | `/admin/usuarios/{usuario_id}/monitoramento` | Ativa ou desativa o monitoramento |
| `GET` | `/admin/obras/legadas` | Lista obras em formato legado |
| `GET` | `/admin/obras/pendentes` | Lista obras pendentes |
| `POST` | `/admin/obras/{obra_id}/status` | Aprova ou rejeita uma obra |
| `GET` | `/admin/eventos` | Consulta eventos de auditoria |

### Obras

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/obras` | Cria uma obra |
| `GET` | `/obras` | Lista e filtra obras |
| `GET` | `/obras/{obra_id}` | Obtém uma obra |
| `POST` | `/obras/{obra_id}` | Atualiza uma obra |
| `DELETE` | `/obras/{obra_id}` | Exclui uma obra |

A listagem aceita `page`, `limit`, `q`, `autor` e `ano`. Respostas paginadas contêm `items` e `pagination`.

### Imagens

| Método | Rota | Descrição |
| --- | --- | --- |
| `POST` | `/obras/{obra_id}/imagens` | Envia uma imagem |
| `GET` | `/obras/{obra_id}/imagens` | Lista as imagens de uma obra |
| `GET` | `/obras/imagens` | Lista todas as imagens acessíveis |
| `GET` | `/obras/imagens/{imagem_id}` | Obtém o arquivo de uma imagem |
| `POST` | `/obras/imagens/{imagem_id}` | Atualiza metadados ou substitui o arquivo |
| `DELETE` | `/obras/imagens/{imagem_id}` | Exclui uma imagem |

As listagens aceitam paginação e filtros por texto, armazenamento e ordem. No upload, envie o arquivo no campo `arquivo`; os campos `descricao` e `ordem` são opcionais.

## Estrutura do projeto

```text
app/
├── core/       # configuração, banco de dados e permissões
├── domain/     # papéis e estados do domínio
├── routers/    # endpoints HTTP
├── schemas/    # modelos de entrada e saída
├── services/   # regras de negócio
├── utils/      # utilitários compartilhados
└── main.py     # criação e configuração da aplicação
uploads/        # imagens quando o backend local está habilitado
```

## Observações

- O JWT contém uma expiração e cada requisição autenticada recarrega o usuário no banco.
- Registros legados de usuários são normalizados durante a leitura.
- Arquivos armazenados localmente são servidos pelo caminho `/uploads`.
- Se existir um diretório `frontend/` com `index.html`, a aplicação também o disponibiliza na rota raiz.
