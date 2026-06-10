# RunPod LTX Video ComfyUI

RunPod Community Cloud template for an LTX 2.3 I2V ComfyUI workflow.

This image bakes ComfyUI custom nodes and `aria2c` into Docker. Large model files are downloaded to `/workspace/comfyui/models` at Pod startup so a persistent volume can reuse them across restarts. By default the downloader runs in the background, so ComfyUI can open while the first model download is still running.

## RunPod Template

Container image:

```text
ghcr.io/YOUR_GITHUB_USER/YOUR_REPO:cuda12.8
```

HTTP port:

```text
ComfyUI 8188
```

Environment variables:

```text
PORT=8188
LISTEN=0.0.0.0
RUN_DEP_CHECK=0
DOWNLOAD_MODELS=1
MODEL_DOWNLOAD_MODE=background
HF_TOKEN={{ RUNPOD_SECRET_HF_TOKEN }}
CIVITAI_TOKEN={{ RUNPOD_SECRET_CIVITAI_TOKEN }}
MODEL_MANIFEST_URL=https://raw.githubusercontent.com/YOUR_GITHUB_USER/YOUR_REPO/main/config/ltx-video-models.json
ARIA2_CONNECTIONS=8
ARIA2_SPLITS=8
DOWNLOAD_JOBS=3
VERIFY_MODEL_HASHES=once
COMFYUI_ARGS=--reserve-vram 5
```

Use RunPod Secrets for `HF_TOKEN` and `CIVITAI_TOKEN`. Do not paste tokens directly into a public template.

### Download behavior

`MODEL_DOWNLOAD_MODE=background` starts ComfyUI immediately. Models are not usable until their downloads finish. Refresh the ComfyUI page after the status becomes `complete`.

Use blocking startup when the HTTP port should open only after every required model is ready:

```text
MODEL_DOWNLOAD_MODE=blocking
```

Check download status and logs from the RunPod terminal:

```bash
cat /workspace/comfyui/logs/model-download.status
tail -f /workspace/comfyui/logs/model-download.log
```

Downloads are written to `*.part` and atomically renamed when complete. Interrupted aria2 downloads are resumed on the next Pod start instead of being mistaken for complete model files.

`VERIFY_MODEL_HASHES=once` verifies files that have a SHA-256 in the manifest and stores a small verification marker. Later boots skip rereading the entire file unless its size or modification time changes.

## Model Storage

Use a Network Volume or persistent `/workspace` volume. The model set is large.

Important real paths:

```text
/workspace/comfyui/models/diffusion_models
/workspace/comfyui/models/checkpoints
/workspace/comfyui/models/text_encoders
/workspace/comfyui/models/vae
/workspace/comfyui/models/latent_upscale_models
/workspace/comfyui/models/loras/ltx23
/workspace/comfyui/models/loras/civitai
```

Startup also creates compatibility symlinks for node dropdowns:

```text
models/checkpoints/LTX23_audio_vae_bf16.safetensors
models/diffusion_models/LTX23_audio_vae_bf16.safetensors
models/checkpoints/LTX23_video_vae_bf16.safetensors
```

## Custom Nodes

Installed during Docker build:

```text
10S-Comfy-nodes
rgthree-comfy
ComfyMath
ComfyUI-VideoHelperSuite
ComfyUI-LTXVideo
RES4LYF
ComfyUI-Custom-Scripts
```

## Workflow

Load this workflow in ComfyUI:

```text
workflows/video_ltx23_i2v_simple.json
```

Replace the missing `LoadImage` input with your own image.

## Notes

The required `10Eros_v1-fp8mixed_learned.safetensors` checkpoint is huge. First boot can still take a long time, but the UI no longer waits for it in background mode. Later boots reuse `/workspace/comfyui/models` and skip completed files.
