#!/usr/bin/env python3
import argparse
import pathlib
import sys


REQUIRED_CUSTOM_NODES = [
    "10S_Nodes",
    "rgthree-comfy",
    "ComfyMath",
    "ComfyUI-VideoHelperSuite",
    "ComfyUI-LTXVideo",
    "RES4LYF",
]

REQUIRED_MODELS = [
    "models/checkpoints/10Eros_v1-fp8mixed_learned.safetensors",
    "models/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors",
    "models/text_encoders/ltx-2.3_text_projection_bf16.safetensors",
    "models/vae/LTX23_video_vae_bf16.safetensors",
    "models/vae/LTX23_audio_vae_bf16.safetensors",
    "models/vae/taeltx2_3.safetensors",
    "models/latent_upscale_models/ltx-2.3-spatial-upscaler-x2-1.1.safetensors",
    "models/loras/ltx23/ltx-2.3-22b-distilled-lora-1.1_fro90_ceil72_condsafe.safetensors",
    "models/loras/ltx23/ltx23_edit_anything_global_rank128_v1_9000steps_adamw.safetensors",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfyui-dir", required=True)
    parser.add_argument("--model-root", required=True)
    args = parser.parse_args()

    comfyui_dir = pathlib.Path(args.comfyui_dir)
    model_root = pathlib.Path(args.model_root)
    errors = []

    for name in REQUIRED_CUSTOM_NODES:
        if not (comfyui_dir / "custom_nodes" / name).exists():
            errors.append(f"missing custom node: {name}")

    for rel in REQUIRED_MODELS:
        path = model_root / rel
        if not path.exists() or path.stat().st_size == 0:
            errors.append(f"missing model: {rel}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Environment looks OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
