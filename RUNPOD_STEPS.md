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
MODEL_DOWNLOAD_MODE=background
HF_TOKEN={{ RUNPOD_SECRET_HF_TOKEN }}
CIVITAI_TOKEN={{ RUNPOD_SECRET_CIVITAI_TOKEN }}
MODEL_MANIFEST_URL=https://raw.githubusercontent.com/YOUR_GITHUB_USER/ltx-video-runpod/main/config/ltx-video-models.json
HF_XET_HIGH_PERFORMANCE=1
HF_HUB_DOWNLOAD_TIMEOUT=120
ARIA2_CONNECTIONS=8
ARIA2_SPLITS=8
DOWNLOAD_JOBS=1
VERIFY_MODEL_HASHES=once
COMFYUI_ARGS=--reserve-vram 5
```

## 4. First Boot

First boot downloads large files. This can still be long:

```text
10Eros_v1-fp8mixed_learned.safetensors   ~29.2 GB
gemma_3_12B_it_fp4_mixed.safetensors     ~9.45 GB
```

After the files are in `/workspace/comfyui/models`, later boots should skip them.

ComfyUI starts before the first download completes. Check readiness in the RunPod terminal:

```bash
cat /workspace/comfyui/logs/model-download.status
tail -f /workspace/comfyui/logs/model-download.log
```

Wait for `complete`, then refresh ComfyUI before loading the workflow. To preserve the old wait-until-ready behavior, set:

```text
MODEL_DOWNLOAD_MODE=blocking
```

Hugging Face files use `hf_xet` high-performance mode. For the shortest future cold starts, keep the completed `/workspace` Network Volume and attach it to later Pods. You can also pre-populate a supported Network Volume through RunPod's S3-compatible API before launching a GPU Pod.

## 5. Load Workflow

Open ComfyUI's **Workflows** list and select:

```text
video_ltx23_i2v_first_last_same.json
```

Replace the missing `LoadImage` file with your own input image.

For the higher-quality two-stage version, select:

```text
video_ltx23_i2v_first_last_same_2stage_hq.json
```

The two-stage workflow generates a roughly 0.5-megapixel first pass, performs
LTX latent x2 spatial upscaling, then runs a four-step refinement pass before
tiled VAE decode. It is slower and needs more VRAM than the original workflow.

For the 10Eros-audio plus DaSiWa-style clearer-video preset, select:

```text
video_ltx23_i2v_first_last_same_dasiwa_hybrid.json
```

This keeps the 10Eros checkpoint/audio VAE path, raises the visual first pass to
0.83 MP, applies the LTX 2.3 spatial latent upscaler, uses a DaSiWa-style
4-step `linear_quadratic` refinement at 0.42 denoise, enables the
`LTX2.3_reasoning_I2V_V3` LoRA, and saves the MP4 at CRF 16. If VRAM is too
tight, use `_2stage_hq` or lower the `SIZE` node in the hybrid workflow.

For a faster DaSiWa-style preset, select:

```text
video_ltx23_i2v_first_last_same_dasiwa_fast.json
```

This keeps the 10Eros audio path, Reasoning I2V LoRA, DaSiWa-style
`linear_quadratic` 4-step refinement, and CRF 16 output, but leaves the first
pass at 0.5 MP and the image guide longer edge at 1536 for much better speed.

For a more natural start-to-end motion with separate first and last images,
select:

```text
video_ltx23_i2v_first_last_pair_dasiwa_fast.json
```

Replace the normal `LoadImage` node with the first frame and the
`Last Frame Image` node with the desired final frame. This preset does not
force-copy the first decoded frame over the end of the video, so it is smoother
for motion but requires the final image to be visually close to the first image
if you want a seamless loop.

The container installs all bundled JSON workflows into
`/workspace/comfyui/user/default/workflows` at startup, including the simple and
perfect-loop variants in one-stage, two-stage, DaSiWa-fast, and DaSiWa-hybrid
form, plus the DaSiWa-fast separate first/last-frame preset.
