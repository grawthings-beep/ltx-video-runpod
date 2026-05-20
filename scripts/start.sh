#!/usr/bin/env bash
set -Eeuo pipefail

source /opt/runpod-ltx/scripts/common.sh

COMFYUI_DIR="$(find_comfyui_dir)" || {
  echo "ERROR: could not find ComfyUI main.py. Set COMFYUI_DIR explicitly." >&2
  exit 2
}

PYTHON_BIN="$(find_python_bin)" || {
  echo "ERROR: neither python nor python3 was found in PATH." >&2
  exit 2
}

WORKSPACE_DIR="${WORKSPACE_DIR:-/workspace/comfyui}"
MODEL_ROOT="${MODEL_ROOT:-${WORKSPACE_DIR}}"
CONFIG_DIR="${CONFIG_DIR:-/workspace/config}"
MODEL_MANIFEST="${MODEL_MANIFEST:-${CONFIG_DIR}/ltx-video-models.json}"
PORT="${PORT:-8188}"
LISTEN="${LISTEN:-0.0.0.0}"

mkdir -p "${WORKSPACE_DIR}/input" \
         "${WORKSPACE_DIR}/output" \
         "${MODEL_ROOT}/models/checkpoints" \
         "${MODEL_ROOT}/models/clip" \
         "${MODEL_ROOT}/models/clip_vision" \
         "${MODEL_ROOT}/models/configs" \
         "${MODEL_ROOT}/models/controlnet" \
         "${MODEL_ROOT}/models/diffusion_models" \
         "${MODEL_ROOT}/models/embeddings" \
         "${MODEL_ROOT}/models/latent_upscale_models" \
         "${MODEL_ROOT}/models/loras/ltx23" \
         "${MODEL_ROOT}/models/style_models" \
         "${MODEL_ROOT}/models/text_encoders" \
         "${MODEL_ROOT}/models/unet" \
         "${MODEL_ROOT}/models/upscale_models" \
         "${MODEL_ROOT}/models/vae" \
         "${MODEL_ROOT}/models/vae_approx" \
         "${CONFIG_DIR}"

write_extra_model_paths() {
  local target="$1"
  cat > "${target}" <<YAML
workspace:
  base_path: ${MODEL_ROOT}
  checkpoints: models/checkpoints/
  clip: models/clip/
  clip_vision: models/clip_vision/
  configs: models/configs/
  controlnet: models/controlnet/
  diffusion_models: models/diffusion_models/
  embeddings: models/embeddings/
  latent_upscale_models: models/latent_upscale_models/
  loras: models/loras/
  style_models: models/style_models/
  text_encoders: models/text_encoders/
  unet: models/unet/
  upscale_models: models/upscale_models/
  vae: models/vae/
  vae_approx: models/vae_approx/
YAML
}

write_extra_model_paths "${COMFYUI_DIR}/extra_model_paths.yaml"
write_extra_model_paths "${COMFYUI_DIR}/extra_model_paths.yml"

if [[ -n "${MODEL_MANIFEST_JSON:-}" ]]; then
  printf '%s' "${MODEL_MANIFEST_JSON}" > "${MODEL_MANIFEST}"
elif [[ -n "${MODEL_MANIFEST_URL:-}" ]]; then
  "${PYTHON_BIN}" - "${MODEL_MANIFEST_URL}" "${MODEL_MANIFEST}" <<'PY'
import pathlib
import sys
import urllib.request

url, output = sys.argv[1], pathlib.Path(sys.argv[2])
output.parent.mkdir(parents=True, exist_ok=True)
request = urllib.request.Request(url, headers={"User-Agent": "runpod-ltx-template"})
with urllib.request.urlopen(request, timeout=60) as response:
    output.write_bytes(response.read())
PY
elif [[ ! -f "${MODEL_MANIFEST}" && -f /opt/runpod-ltx/config/ltx-video-models.json ]]; then
  cp /opt/runpod-ltx/config/ltx-video-models.json "${MODEL_MANIFEST}"
fi

if [[ "${DOWNLOAD_MODELS:-1}" == "1" && -f "${MODEL_MANIFEST}" ]]; then
  "${PYTHON_BIN}" /opt/runpod-ltx/scripts/download_models.py \
    --manifest "${MODEL_MANIFEST}" \
    --root "${MODEL_ROOT}"
else
  echo "Skipping model downloads."
fi

link_if_present() {
  local source="$1"
  local target="$2"
  if [[ -f "${source}" ]]; then
    mkdir -p "$(dirname "${target}")"
    ln -sf "${source}" "${target}"
  fi
}

# Compatibility aliases for LTX nodes whose dropdowns read different model folders.
link_if_present \
  "${MODEL_ROOT}/models/vae/LTX23_audio_vae_bf16.safetensors" \
  "${MODEL_ROOT}/models/checkpoints/LTX23_audio_vae_bf16.safetensors"
link_if_present \
  "${MODEL_ROOT}/models/vae/LTX23_audio_vae_bf16.safetensors" \
  "${MODEL_ROOT}/models/diffusion_models/LTX23_audio_vae_bf16.safetensors"
link_if_present \
  "${MODEL_ROOT}/models/vae/LTX23_video_vae_bf16.safetensors" \
  "${MODEL_ROOT}/models/checkpoints/LTX23_video_vae_bf16.safetensors"

if [[ "${RUN_DEP_CHECK:-0}" == "1" ]]; then
  "${PYTHON_BIN}" /opt/runpod-ltx/scripts/check_env.py --comfyui-dir "${COMFYUI_DIR}" --model-root "${MODEL_ROOT}"
fi

cd "${COMFYUI_DIR}"
exec "${PYTHON_BIN}" main.py \
  --listen "${LISTEN}" \
  --port "${PORT}" \
  --enable-cors-header "${COMFYUI_CORS_ORIGIN:-*}" \
  --input-directory "${WORKSPACE_DIR}/input" \
  --output-directory "${WORKSPACE_DIR}/output" \
  ${COMFYUI_ARGS:-}
