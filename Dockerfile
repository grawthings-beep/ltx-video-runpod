ARG BASE_IMAGE=runpod/comfyui:latest
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        aria2 \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY custom_nodes.txt /opt/runpod-ltx/custom_nodes.txt
COPY config/ /opt/runpod-ltx/config/
COPY scripts/ /opt/runpod-ltx/scripts/

RUN chmod +x /opt/runpod-ltx/scripts/*.sh \
    && /opt/runpod-ltx/scripts/install_custom_nodes.sh

EXPOSE 8188

ENTRYPOINT []
CMD ["/opt/runpod-ltx/scripts/start.sh"]
