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
MODEL_DOWNLOAD_MODE="${MODEL_DOWNLOAD_MODE:-background}"
MODEL_DOWNLOAD_LOG_DIR="${MODEL_DOWNLOAD_LOG_DIR:-${WORKSPACE_DIR}/logs}"
MODEL_DOWNLOAD_LOG="${MODEL_DOWNLOAD_LOG:-${MODEL_DOWNLOAD_LOG_DIR}/model-download.log}"
MODEL_DOWNLOAD_STATUS="${MODEL_DOWNLOAD_STATUS:-${MODEL_DOWNLOAD_LOG_DIR}/model-download.status}"
MODEL_DOWNLOAD_LOCK="${MODEL_DOWNLOAD_LOCK:-${MODEL_DOWNLOAD_LOG_DIR}/model-download.lock}"
PORT="${PORT:-8188}"
LISTEN="${LISTEN:-0.0.0.0}"

mkdir -p "${WORKSPACE_DIR}/input" \
         "${WORKSPACE_DIR}/output" \
         "${MODEL_DOWNLOAD_LOG_DIR}" \
         "${MODEL_ROOT}/models/checkpoints" \
         "${MODEL_ROOT}/models/clip" \
         "${MODEL_ROOT}/models/clip_vision" \
         "${MODEL_ROOT}/models/configs" \
         "${MODEL_ROOT}/models/controlnet" \
         "${MODEL_ROOT}/models/diffusion_models" \
         "${MODEL_ROOT}/models/embeddings" \
         "${MODEL_ROOT}/models/latent_upscale_models" \
         "${MODEL_ROOT}/models/loras/civitai" \
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
  if ! "${PYTHON_BIN}" - "${MODEL_MANIFEST_URL}" "${MODEL_MANIFEST}" <<'PY'
import pathlib
import sys
import urllib.request

url, output = sys.argv[1], pathlib.Path(sys.argv[2])
output.parent.mkdir(parents=True, exist_ok=True)
request = urllib.request.Request(url, headers={"User-Agent": "runpod-ltx-template"})
temporary = output.with_name(output.name + ".tmp")
with urllib.request.urlopen(request, timeout=30) as response:
    temporary.write_bytes(response.read())
temporary.replace(output)
PY
  then
    if [[ -f "${MODEL_MANIFEST}" ]]; then
      echo "WARN: could not refresh model manifest; using existing ${MODEL_MANIFEST}" >&2
    elif [[ -f /opt/runpod-ltx/config/ltx-video-models.json ]]; then
      echo "WARN: could not download model manifest; using image-bundled copy" >&2
      cp /opt/runpod-ltx/config/ltx-video-models.json "${MODEL_MANIFEST}"
    else
      echo "ERROR: could not download model manifest and no fallback exists." >&2
      exit 2
    fi
  fi
elif [[ ! -f "${MODEL_MANIFEST}" && -f /opt/runpod-ltx/config/ltx-video-models.json ]]; then
  cp /opt/runpod-ltx/config/ltx-video-models.json "${MODEL_MANIFEST}"
fi

link_model_alias() {
  local source="$1"
  local target="$2"
  mkdir -p "$(dirname "${target}")"
  ln -sfn "${source}" "${target}"
}

create_model_aliases() {
  # Compatibility aliases for LTX nodes whose dropdowns read different folders.
  link_model_alias \
    "${MODEL_ROOT}/models/vae/LTX23_audio_vae_bf16.safetensors" \
    "${MODEL_ROOT}/models/checkpoints/LTX23_audio_vae_bf16.safetensors"
  link_model_alias \
    "${MODEL_ROOT}/models/vae/LTX23_audio_vae_bf16.safetensors" \
    "${MODEL_ROOT}/models/diffusion_models/LTX23_audio_vae_bf16.safetensors"
  link_model_alias \
    "${MODEL_ROOT}/models/vae/LTX23_video_vae_bf16.safetensors" \
    "${MODEL_ROOT}/models/checkpoints/LTX23_video_vae_bf16.safetensors"
}

run_dependency_check() {
  if [[ "${RUN_DEP_CHECK:-0}" == "1" ]]; then
    "${PYTHON_BIN}" /opt/runpod-ltx/scripts/check_env.py \
      --comfyui-dir "${COMFYUI_DIR}" \
      --model-root "${MODEL_ROOT}"
  fi
}

write_download_status() {
  printf '%s %s\n' "$1" "$(date -Iseconds)" > "${MODEL_DOWNLOAD_STATUS}"
}

run_model_downloads() {
  local status
  write_download_status "running"
  echo "Model download started. Log: ${MODEL_DOWNLOAD_LOG}"
  if "${PYTHON_BIN}" /opt/runpod-ltx/scripts/download_models.py \
    --manifest "${MODEL_MANIFEST}" \
    --root "${MODEL_ROOT}"; then
    create_model_aliases
    if run_dependency_check; then
      write_download_status "complete"
      echo "Model download completed."
      return 0
    else
      status=$?
    fi
  else
    status=$?
  fi

  write_download_status "failed"
  echo "ERROR: model download failed with status ${status}. See ${MODEL_DOWNLOAD_LOG}" >&2
  return "${status}"
}

start_background_downloads() {
  (
    exec 9> "${MODEL_DOWNLOAD_LOCK}"
    if command -v flock >/dev/null 2>&1 && ! flock -n 9; then
      echo "Another model downloader already holds ${MODEL_DOWNLOAD_LOCK}; continuing with ComfyUI."
      exit 0
    fi
    run_model_downloads
  ) > >(tee -a "${MODEL_DOWNLOAD_LOG}") 2>&1 &
  local download_pid=$!
  printf '%s\n' "${download_pid}" > "${MODEL_DOWNLOAD_LOG_DIR}/model-download.pid"
  echo "Model download is running in the background (PID ${download_pid})."
}

create_model_aliases

if [[ "${DOWNLOAD_MODELS:-1}" != "1" || ! -f "${MODEL_MANIFEST}" ]]; then
  echo "Skipping model downloads."
  run_dependency_check
else
  case "${MODEL_DOWNLOAD_MODE}" in
    background)
      start_background_downloads
      ;;
    blocking)
      run_model_downloads
      ;;
    *)
      echo "ERROR: MODEL_DOWNLOAD_MODE must be 'background' or 'blocking'." >&2
      exit 2
      ;;
  esac
fi

cd "${COMFYUI_DIR}"
echo "Starting ComfyUI on ${LISTEN}:${PORT} (model download mode: ${MODEL_DOWNLOAD_MODE})."
exec "${PYTHON_BIN}" main.py \
  --listen "${LISTEN}" \
  --port "${PORT}" \
  --enable-cors-header "${COMFYUI_CORS_ORIGIN:-*}" \
  --input-directory "${WORKSPACE_DIR}/input" \
  --output-directory "${WORKSPACE_DIR}/output" \
  ${COMFYUI_ARGS:-}
