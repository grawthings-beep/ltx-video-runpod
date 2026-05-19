# RunPod Steps

## 1. Create GitHub Repo

Example repo name:

```text
ltx-video-runpod
```

Push this folder to GitHub:

```bash
git init
git add .
git commit -m "Add RunPod LTX Video ComfyUI image"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USER/ltx-video-runpod.git
git push -u origin main
```

## 2. Wait For GitHub Actions

Open:

```text
https://github.com/YOUR_GITHUB_USER/ltx-video-runpod/actions
```

Wait until `Build GHCR image` is green.

## 3. RunPod Template

Container image:

```text
ghcr.io/YOUR_GITHUB_USER/ltx-video-runpod:cuda12.8
```

HTTP port:

```text
ComfyUI 8188
```

Recommended disk:

```text
Container disk: 40 GB+
Volume / Network Volume: 120 GB+
Volume mount path: /workspace
```

Environment variables:

```text
PORT=8188
LISTEN=0.0.0.0
RUN_DEP_CHECK=0
DOWNLOAD_MODELS=1
HF_TOKEN={{ RUNPOD_SECRET_HF_TOKEN }}
MODEL_MANIFEST_URL=https://raw.githubusercontent.com/YOUR_GITHUB_USER/ltx-video-runpod/main/config/ltx-video-models.json
ARIA2_CONNECTIONS=16
ARIA2_SPLITS=16
COMFYUI_ARGS=--reserve-vram 5
```

## 4. First Boot

First boot downloads large files. This can still be long:

```text
10Eros_v1_fp8_transformer.safetensors    ~29.6 GB
gemma_3_12B_it_fp4_mixed.safetensors     ~9.45 GB
```

After the files are in `/workspace/comfyui/models`, later boots should skip them.

## 5. Load Workflow

Load this workflow in ComfyUI:

```text
workflows/video_ltx23_i2v_simple.json
```

Replace the missing `LoadImage` file with your own input image.
