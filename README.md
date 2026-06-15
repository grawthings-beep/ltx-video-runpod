# RunPod LTX Video ComfyUI

RunPod Community Cloud template for an LTX 2.3 I2V ComfyUI workflow.

This image bakes ComfyUI custom nodes, Hugging Face `hf_xet`, and `aria2c` into Docker. Hugging Face files use the Hub's Xet transfer path; other hosts use resumable curl/aria2 downloads. Large model files are stored in `/workspace/comfyui/models` so a persistent volume can reuse them across restarts. By default the downloader runs in the background, so ComfyUI can open while the first model download is still running.

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
HF_XET_HIGH_PERFORMANCE=1
HF_HUB_DOWNLOAD_TIMEOUT=120
ARIA2_CONNECTIONS=8
ARIA2_SPLITS=8
DOWNLOAD_JOBS=1
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

### Fastest download options

For direct Hugging Face downloads, the image uses `hf_xet` with `HF_XET_HIGH_PERFORMANCE=1`. This is the current Hugging Face high-performance transfer path and attempts to saturate the machine's network bandwidth and CPU. `DOWNLOAD_JOBS=1` is intentional because Xet already downloads chunks concurrently inside each file.

The equivalent manual command is:

```bash
HF_XET_HIGH_PERFORMANCE=1 hf download \
  TenStrip/LTX2.3-10Eros \
  10Eros_v1-fp8mixed_learned.safetensors \
  --local-dir /workspace/comfyui/models/checkpoints
```

Copying the same files into a personal Hugging Face repository normally does not improve speed because it still uses the same Hub storage and transfer backend. It also adds redistribution and license-management concerns.

The fastest repeatable Pod startup is to attach a RunPod Network Volume that already contains the models. RunPod's S3-compatible API can pre-populate the volume without running a GPU Pod; then startup performs no internet model transfer.

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
ComfyUI-KJNodes
```

## Workflow

Bundled workflows are installed at startup into:

```text
/workspace/comfyui/user/default/workflows
```

They appear in ComfyUI's **Workflows** list:

```text
video_ltx23_i2v_simple.json
video_ltx23_i2v_first_last_same.json
video_ltx23_i2v_simple_2stage_hq.json
video_ltx23_i2v_first_last_same_2stage_hq.json
```

Select `video_ltx23_i2v_first_last_same.json` for the perfect-loop workflow,
then replace the missing `LoadImage` input with your own image.

Select a `_2stage_hq` workflow when output quality matters more than minimum
generation time. These workflows:

- Generate the first pass at about 0.5 megapixels with the existing distilled
  8-step pipeline.
- Upscale the stage-one video latent by 2x in each spatial dimension with
  `ltx-2.3-spatial-upscaler-x2-1.1.safetensors`.
- Re-apply the source image guide at the higher latent resolution.
- Run a four-step refinement pass with the official LTX 2.3 distilled sigma
  schedule used by ComfyUI's two-stage workflow.
- Decode the roughly 2-megapixel result with tiled VAE decode to reduce the
  peak VRAM requirement.

The two-stage workflow is substantially slower than the original simple
workflow and uses more VRAM, but it preserves detail better than applying a
pixel-space upscaler after video generation.

All bundled workflows load `10Eros_v1-fp8mixed_learned.safetensors` as a full
checkpoint. Its bundled video VAE is used for image guides and video decode,
and `LTXVAudioVAELoader` reads the bundled audio VAE from the same checkpoint.
This matches the model author's workflow instead of mixing in VAE files from a
different split-model distribution.

The sampling preview override uses its built-in LTX 2.3 latent-to-RGB preview.
The optional TAE preview VAE is deliberately left disconnected because it can
produce an all-black progress preview on some ComfyUI/KJNodes combinations.
This preview setting does not change the final VAE decode.

It reuses the single `LoadImage` input at frame `0` and frame `-1` (the final
frame), so the endpoint follows changes to duration and frame rate automatically.
The first-frame guide uses `0.9`, matching the simple workflow. The last-frame
guide is deliberately softer at `0.35` so the image condition does not overpower
the prompt and LoRAs. In the two-stage loop workflow, the refinement pass uses
even softer `0.7` and `0.2` endpoint guides to avoid applying the same image
condition at full strength twice.

After decoding, the workflow also copies decoded frame `0` over frame `-1`
immediately before `VHS_VideoCombine`. This preserves the frame count and makes
the rendered image sequence close with identical first and last frames.

`VHS_VideoCombine` saves completed videos under
`/workspace/comfyui/output` by default. The image also installs system ffmpeg
explicitly instead of relying on whichever ffmpeg happens to be present in the
base image.

The RunPod ComfyUI base image and every custom-node revision are pinned so a
rebuild does not silently change the runtime.

The ComfyUI user directory lives under `/workspace`, so workflows and UI settings
persist when that path is backed by a Network Volume.

## Notes

The required `10Eros_v1-fp8mixed_learned.safetensors` checkpoint is huge. First boot can still take a long time, but the UI no longer waits for it in background mode. Later boots reuse `/workspace/comfyui/models` and skip completed files.
