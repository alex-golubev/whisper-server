import io
import os

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from faster_whisper import WhisperModel

app = FastAPI()
model = WhisperModel('small', device='cpu', compute_type='int8')

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
