FROM nousresearch/hermes-agent:latest

USER root

# Capabilities we want available on day one rather than lazily installed:
# - voice/audio plumbing
# - deterministic OCR/document handling
# - basic remote/admin tooling used by Leto's terminal work
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libopus0 \
        portaudio19-dev \
        espeak-ng \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
        ocrmypdf \
        openssh-client \
        rsync \
    && rm -rf /var/lib/apt/lists/*

# Hermes intentionally keeps several capabilities optional/lazy upstream.
# In our container image they are explicit so launch never depends on a
# runtime package install.
RUN /opt/hermes/.venv/bin/python -m pip install --no-cache-dir \
        faster-whisper \
        edge-tts \
        "discord.py[voice]" \
        firecrawl-anydoc

USER hermes
