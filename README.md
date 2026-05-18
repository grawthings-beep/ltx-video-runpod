# RunPod LTX Video ComfyUI

RunPod Community Cloud 用の ComfyUI LTX Video テンプレートです。

この image は ComfyUI 本体、LTX 系 custom nodes、`aria2c` を Docker image に焼きます。巨大なモデルは `/workspace/comfyui/models` に起動時ダウンロードします。

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

Use a Network Volume or persistent `/workspace` volume. The full workflow model set is very large.

Important paths:

```text
/workspace/comfyui/models/diffusion_models
/workspace/comfyui/models/checkpoints
/workspace/comfyui/models/text_encoders
/workspace/comfyui/models/vae
/workspace/comfyui/models/latent_upscale_models
/workspace/comfyui/models/loras/ltx23
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
```

## Workflow

Load the JSON from `workflows/` into ComfyUI. Replace the missing `LoadImage` input with your own image.

The generated MP4 analyzed from the matching workflow was:

```text
896x1664
about 10 seconds
24 fps
H.264 video + AAC audio
```

## Notes

The required `10Eros_v1_bf16.safetensors` and `10Eros_v1_fp8_transformer.safetensors` files are huge. First boot can still take a long time. The win is that later boots reuse `/workspace/comfyui/models` instead of redownloading.
