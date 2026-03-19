# Whisper Server

Self-hosted speech transcription server powered by [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`medium` model, int8, CPU).

## Stack

- Python 3.11, FastAPI, uvicorn
- faster-whisper (CTranslate2)
- Docker + Docker Compose
- Caddy (automatic HTTPS)

## API

### `POST /transcribe`

Transcribe an audio file. Requires authorization.

```bash
curl -X POST https://whisper.sonavera.io/transcribe \
  -H "Authorization: Bearer <token>" \
  -F "audio=@file.wav"
```

Response:
```json
{"text": "hello how are you", "language": "en"}
```

### `GET /health`

Health check, no authorization required.

```json
{"status": "ok"}
```

## Deployment

### VPS requirements

- Docker + Docker Compose
- ~4GB RAM
- Domain with A record pointing to server IP

### GitHub Secrets

Add in Settings → Secrets and variables → Actions:

| Secret | Description |
|--------|-------------|
| `VPS_HOST` | Server IP address |
| `VPS_USER` | SSH username |
| `VPS_SSH_KEY` | Private SSH key |

### VPS setup (once)

1. Install Docker:
```bash
curl -fsSL https://get.docker.com | sh
```

2. Configure firewall:
```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8765
sudo ufw enable
```

3. Create `.env`:
```bash
mkdir -p ~/whisper-server
nano ~/whisper-server/.env
```
```
AUTH_TOKEN=<openssl rand -hex 32>
DOMAIN=whisper.yourdomain.com
```

4. Trigger deploy via Actions → Deploy → Run workflow, or push to `main`.

### How deployment works

1. Push to `main` (or manual trigger)
2. GitHub Action builds Docker image → pushes to GitHub Container Registry
3. Action copies `docker-compose.yml` to VPS via SCP
4. Action connects via SSH, pulls the image, restarts containers
