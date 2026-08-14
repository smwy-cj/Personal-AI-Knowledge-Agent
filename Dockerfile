FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PERSONAL_AGENT_CONFIG=/app/course_demo/config.json \
    PERSONAL_AGENT_DEMO_MODE=1 \
    PERSONAL_AGENT_DEMO_DATA_ROOT=/app/course_demo \
    PERSONAL_AGENT_WEB_HOST=0.0.0.0

WORKDIR /app

RUN groupadd --system agent && useradd --system --gid agent --home-dir /app agent

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir .

COPY course_demo/config.json ./course_demo/config.json
COPY course_demo/vault ./course_demo/vault
RUN mkdir -p /app/course_demo/runtime && chown -R agent:agent /app/course_demo

USER agent

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.environ.get('PORT', '8000'); urllib.request.urlopen('http://127.0.0.1:'+port+'/health', timeout=2).read()"

CMD ["personal-ai-agent-demo"]
