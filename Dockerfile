# eman — 实验数据记录与管理（FastAPI + SQLite）
FROM python:3.12-slim

ARG VERSION=0.1.0
LABEL org.opencontainers.image.title="eman" \
      org.opencontainers.image.description="实验数据记录与管理（FastAPI + SQLite）" \
      org.opencontainers.image.source="https://github.com/aixia715/eman" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# 依赖单独一层，改代码时不必重装
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY eman/ ./eman/
COPY static/ ./static/

# create_app() 默认把 SQLite 建在“当前工作目录”下的 eman.db，
# 因此把工作目录设为数据卷 /data，容器重建后数据仍在。
# 附件与正文插图的字节同样存在这个文件里，备份 = 复制 /data/eman.db。
RUN mkdir -p /data \
    && useradd --system --create-home --uid 10001 eman \
    && chown eman:eman /data
VOLUME ["/data"]
WORKDIR /data
USER eman

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/experiments').read()"

CMD ["uvicorn", "--factory", "eman.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
