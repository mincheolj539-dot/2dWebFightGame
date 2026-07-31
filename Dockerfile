# 대전 서버(WebSocket) 컨테이너 이미지 — NAS/Portainer 등 Docker 환경용.
# 렌더링은 하지 않지만 game/fighter.py 가 pygame 을 import 하므로 pygame-ce 도 설치한다.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY server/requirements.txt server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY game/ game/
COPY server/ server/

ENV PORT=8765
EXPOSE 8765
CMD ["python", "server/server.py"]
