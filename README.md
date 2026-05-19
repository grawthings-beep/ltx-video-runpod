# RunPod LTX Video ComfyUI

RunPod Community Cloud template for an LTX 2.3 I2V ComfyUI workflow.

This image bakes ComfyUI custom nodes and `aria2c` into Docker. Large model files are downloaded to `/workspace/comfyui/models` at Pod startup so a persistent volume can reuse them across restarts.

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
HF_TOKEN={{ RUNPOD_SECRET_HF_TOKEN }}
MODEL_MANIFEST_URL=https://raw.githubusercontent.com/YOUR_GITHUB_USER/YOUR_REPO/main/config/ltx-video-models.json
ARIA2_CONNECTIONS=16
ARIA2_SPLITS=16
COMFYUI_ARGS=--reserve-vram 5
```

Use a RunPod Secret for `HF_TOKEN`. Do not paste the token directly into a public template.

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
```

Startup also creates compatibility symlinks for node dropdowns:

```text
models/checkpoints/10Eros_v1_fp8_transformer.safetensors
models/unet/10Eros_v1_fp8_transformer.safetensors
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

The required `10Eros_v1_fp8_transformer.safetensors` file is huge. First boot can still take a long time. Later boots reuse `/workspace/comfyui/models` and skip existing files.
