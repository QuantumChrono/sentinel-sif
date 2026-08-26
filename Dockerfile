# Backend container for Hugging Face Spaces (SDK: docker — see the frontmatter in README.md).
#
# WHY THIS SITS AT THE REPO ROOT AND NOT IN `backend/`. An HF Space is its own git repo and
# builds the Dockerfile at ITS root. The Space is this same repo pushed to a second remote, so
# the Dockerfile has to be here to be found. It copies only `backend/`, so nothing about the
# frontend enters the image. Vercel is unaffected: its Root Directory is `frontend/`.
#
# NO ML LIBRARIES AND NO WEIGHTS ARE INSTALLED. Inference today is the INTERIM_LANE_A keyword
# implementation — pure Python and `re`, zero model files. `backend/requirements.txt` is the
# whole dependency list. See README.md § Model weights for what changes after Block 8.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Requirements first so a code-only change does not reinstall dependencies.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Non-root, uid 1000: the convention HF Spaces expects, and the app never writes to disk anyway.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 7860 is the HF Spaces default and must match `app_port` in README.md. `0.0.0.0` because
# 127.0.0.1 inside a container is unreachable from outside it.
EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
