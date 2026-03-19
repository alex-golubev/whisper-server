# Whisper Server — развертывание на VPS

## Контекст

Gemini `inputAudioTranscription` выдает мусор при транскрипции речи пользователя. Self-hosted Whisper сервер на VPS обеспечивает качественную транскрипцию. Сервер живет в отдельном репо (`whisper-server`), деплоится на VPS с 4GB RAM. Sonavera (Next.js на Vercel) обращается к нему через HTTPS с bearer-токеном.

## Стек

- Python 3.11 + FastAPI + uvicorn (1 воркер)
- faster-whisper (CTranslate2) — модель `medium`, мультиязычная, int8
- Docker + Docker Compose
- Caddy — reverse proxy, автоматический HTTPS через Let's Encrypt

## Требования к VPS

- Docker + Docker Compose
- ~4GB RAM (1 воркер × ~2.5GB + система)
- ~1GB диска (модель скачается при первом запуске)
- Домен с A-записью, указывающей на IP VPS

## Пропускная способность

Модель `medium` с `beam_size=1` на CPU обрабатывает фразу за ~2–5 секунд. 1 воркер дает ~20–30 транскрипций в минуту. В разговорном приложении (фраза раз в 10–15 секунд) это обслуживает ~8–10 одновременных пользователей. При росте нагрузки — добавить воркеры и апгрейд RAM.

## Структура репо

```
whisper-server/
├── server.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Файлы

### `requirements.txt`

```
fastapi
uvicorn[standard]
faster-whisper
python-multipart
```

### `server.py`

```python
import io
import os

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from faster_whisper import WhisperModel

app = FastAPI()
model = WhisperModel('medium', device='cpu', compute_type='int8')

AUTH_TOKEN = os.environ['AUTH_TOKEN']


def verify_token(authorization: str = Header()):
    if authorization != f'Bearer {AUTH_TOKEN}':
        raise HTTPException(status_code=401, detail='Unauthorized')


@app.post('/transcribe', dependencies=[Depends(verify_token)])
async def transcribe(audio: UploadFile):
    contents = await audio.read()
    segments, info = model.transcribe(
        io.BytesIO(contents),
        beam_size=1,
        vad_filter=True,
    )
    text = ' '.join(s.text.strip() for s in segments)
    return {'text': text, 'language': info.language}


@app.get('/health')
async def health():
    return {'status': 'ok'}
```

- `AUTH_TOKEN` из env — общий секрет с Vercel
- `Depends(verify_token)` — FastAPI dependency injection, проверяет `Authorization: Bearer <token>` до выполнения handler'а
- `/health` без авторизации — для мониторинга
- `beam_size=1` + `vad_filter=True` — максимальная скорость на CPU

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 8765

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8765"]
```

- 1 воркер по умолчанию (~2.5GB RAM на модель `medium`)
- Порт 8765 — внутренний, наружу не открывается

### `docker-compose.yml`

```yaml
services:
  whisper:
    build: .
    env_file: .env
    ports:
      - "127.0.0.1:8765:8765"
    volumes:
      - whisper-cache:/root/.cache
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 3G

  caddy:
    image: caddy:2-alpine
    command: caddy reverse-proxy --from ${DOMAIN} --to whisper:8765
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - caddy-data:/data
      - caddy-config:/config
    env_file: .env
    restart: unless-stopped
    depends_on:
      - whisper

volumes:
  whisper-cache:
  caddy-data:
  caddy-config:
```

- `127.0.0.1:8765:8765` — whisper слушает ТОЛЬКО на localhost, не доступен снаружи
- Caddy запускается через `command` с `--from ${DOMAIN}` — домен берётся из `.env`, отдельный `Caddyfile` не нужен
- Caddy автоматически получает и обновляет TLS-сертификат через Let's Encrypt
- `whisper-cache` сохраняет скачанную модель между перезапусками
- `caddy-data` хранит TLS-сертификаты

### `.env.example`

```
AUTH_TOKEN=your-secret-token-here
DOMAIN=whisper.yourdomain.com
```

Генерация токена:
```bash
openssl rand -hex 32
```

## Развертывание

### 1. Установить Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# перелогиниться
```

### 2. Настроить firewall

```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP (Caddy redirect → HTTPS)
sudo ufw allow 443/tcp   # HTTPS (Caddy)
sudo ufw deny 8765       # явно закрыть порт Whisper снаружи
sudo ufw enable
```

### 3. Настроить DNS

В панели управления доменом (Vercel Domains) добавить A-запись:
```
whisper.yourdomain.com → <IP VPS>
```

### 4. Запустить

```bash
git clone <repo-url> whisper-server
cd whisper-server
cp .env.example .env
# отредактировать .env — подставить AUTH_TOKEN и DOMAIN
docker compose up -d --build
```

Первый запуск: ~3–5 минут (скачивание модели ~500MB).

### 5. Проверить

```bash
# health check (без авторизации)
curl https://whisper.yourdomain.com/health

# транскрипция (с авторизацией)
curl -X POST https://whisper.yourdomain.com/transcribe \
  -H "Authorization: Bearer <token>" \
  -F "audio=@test.wav"

# без токена — должен вернуть 401
curl -X POST https://whisper.yourdomain.com/transcribe \
  -F "audio=@test.wav"
```

Ожидаемые ответы:
```json
{"status": "ok"}
{"text": "hello how are you", "language": "en"}
{"detail": "Unauthorized"}
```

### 6. Проверить логи

```bash
docker compose logs whisper   # модель загружена, нет ошибок
docker compose logs caddy     # TLS-сертификат получен
```

## Интеграция с Sonavera

После запуска сервера, добавить в `.env.local` проекта Sonavera:

```
WHISPER_URL=https://whisper.yourdomain.com
WHISPER_AUTH_TOKEN=<тот же токен>
```

И на Vercel в Environment Variables — те же две переменные.

Дальнейшая интеграция на стороне приложения описана в `dev-docs/whisper-transcription.md`.
