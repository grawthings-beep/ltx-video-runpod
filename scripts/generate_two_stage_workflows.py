#!/usr/bin/env python3
import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / "workflows"
UPSCALE_MODEL = "ltx-2.3-spatial-upscaler-x2-1.1.safetensors"
SECOND_STAGE_SIGMAS = "0.85, 0.7250, 0.4219, 0.0"
FIRST_STAGE_MEGAPIXELS = 0.5
LOOP_SECOND_STAGE_GUIDE_VALUES = ["2", 0, 0.7, -1, 0.2]
DASIWA_FIRST_STAGE_MEGAPIXELS = 0.83
DASIWA_SECOND_STAGE_SCHEDULER = "linear_quadratic"
DASIWA_SECOND_STAGE_STEPS = 4
DASIWA_SECOND_STAGE_DENOISE = 0.42
DASIWA_REASONING_LORA = "ltx23/LTX2.3_reasoning_I2V_V3.safetensors"
DASIWA_REASONING_LORA_STRENGTH = 1
DASIWA_DISTILLED_LORA_STRENGTH = 0.5
DASIWA_GUIDE_LONG_EDGE = 1920
DASIWA_VIDEO_CRF = 16

TARGETS = {
    "video_ltx23_i2v_simple.json": "video_ltx23_i2v_simple_2stage_hq.json",
    "video_ltx23_i2v_first_last_same.json": (
        "video_ltx23_i2v_first_last_same_2stage_hq.json"
    ),
}

DASIWA_HYBRID_TARGETS = {
    "video_ltx23_i2v_simple.json": "video_ltx23_i2v_simple_dasiwa_hybrid.json",
    "video_ltx23_i2v_first_last_same.json": (
        "video_ltx23_i2v_first_last_same_dasiwa_hybrid.json"
    ),
}


def node_by_id(workflow, node_id):
    return next(node for node in workflow["nodes"] if node["id"] == node_id)


def clone_node(workflow, node_id, new_id, position, title=None):
    node = copy.deepcopy(node_by_id(workflow, node_id))
    node["id"] = new_id
    node["pos"] = list(position)
    node["order"] = max(item.get("order", 0) for item in workflow["nodes"]) + 1
    if title is not None:
        node["title"] = title
    for item in node.get("inputs", []):
        item["link"] = None
    for item in node.get("outputs", []):
        item["links"] = []
    return node


def add_link(workflow, origin_id, origin_slot, target_id, target_slot, link_type):
    workflow["last_link_id"] += 1
    link_id = workflow["last_link_id"]
    workflow["links"].append(
        [link_id, origin_id, origin_slot, target_id, target_slot, link_type]
    )

    origin = node_by_id(workflow, origin_id)
    links = origin["outputs"][origin_slot].get("links")
    if not isinstance(links, list):
        links = []
        origin["outputs"][origin_slot]["links"] = links
    links.append(link_id)

    target = node_by_id(workflow, target_id)
    target["inputs"][target_slot]["link"] = link_id
    return link_id


def remove_target_link(workflow, target_id, target_slot):
    target = node_by_id(workflow, target_id)
    link_id = target["inputs"][target_slot].get("link")
    if link_id is None:
        return

    link = next(item for item in workflow["links"] if item[0] == link_id)
    origin = node_by_id(workflow, link[1])
    origin_links = origin["outputs"][link[2]].get("links")
    if isinstance(origin_links, list):
        origin["outputs"][link[2]]["links"] = [
            item for item in origin_links if item != link_id
        ]
    workflow["links"] = [item for item in workflow["links"] if item[0] != link_id]
    target["inputs"][target_slot]["link"] = None


def new_node_id(workflow):
    workflow["last_node_id"] += 1
    return workflow["last_node_id"]


def add_core_node(workflow, node):
    node["order"] = max(item.get("order", 0) for item in workflow["nodes"]) + 1
    workflow["nodes"].append(node)
    return node["id"]


def make_upscale_loader(workflow):
    node_id = new_node_id(workflow)
    return add_core_node(
        workflow,
        {
            "id": node_id,
            "type": "LatentUpscaleModelLoader",
            "title": "LTX 2.3 SPATIAL UPSCALER x2",
            "pos": [3840, 6030],
            "size": [400, 110],
            "flags": {},
            "mode": 0,
            "inputs": [
                {
                    "name": "model_name",
                    "type": "COMBO",
                    "widget": {"name": "model_name"},
                    "link": None,
                }
            ],
            "outputs": [
                {
                    "name": "LATENT_UPSCALE_MODEL",
                    "type": "LATENT_UPSCALE_MODEL",
                    "links": [],
                }
            ],
            "properties": {
                "Node name for S&R": "LatentUpscaleModelLoader",
                "cnr_id": "comfy-core",
            },
            "widgets_values": [UPSCALE_MODEL],
        },
    )


def make_latent_upsampler(workflow):
    node_id = new_node_id(workflow)
    return add_core_node(
        workflow,
        {
            "id": node_id,
            "type": "LTXVLatentUpsampler",
            "title": "LATENT x2 UPSCALE",
            "pos": [4140, 5850],
            "size": [300, 120],
            "flags": {},
            "mode": 0,
            "inputs": [
                {"name": "samples", "type": "LATENT", "link": None},
                {
                    "name": "upscale_model",
                    "type": "LATENT_UPSCALE_MODEL",
                    "link": None,
                },
                {"name": "vae", "type": "VAE", "link": None},
            ],
            "outputs": [{"name": "LATENT", "type": "LATENT", "links": []}],
            "properties": {
                "Node name for S&R": "LTXVLatentUpsampler",
                "cnr_id": "comfy-core",
            },
        },
    )


def make_manual_sigmas(workflow):
    node_id = new_node_id(workflow)
    return add_core_node(
        workflow,
        {
            "id": node_id,
            "type": "ManualSigmas",
            "title": "2ND PASS: 4 STEPS",
            "pos": [4770, 5845],
            "size": [320, 110],
            "flags": {},
            "mode": 0,
            "inputs": [
                {
                    "name": "sigmas",
                    "type": "STRING",
                    "widget": {"name": "sigmas"},
                    "link": None,
                }
            ],
            "outputs": [{"name": "SIGMAS", "type": "SIGMAS", "links": []}],
            "properties": {
                "Node name for S&R": "ManualSigmas",
                "cnr_id": "comfy-core",
            },
            "widgets_values": [SECOND_STAGE_SIGMAS],
        },
    )


def make_basic_scheduler(workflow):
    node_id = new_node_id(workflow)
    return add_core_node(
        workflow,
        {
            "id": node_id,
            "type": "BasicScheduler",
            "title": "2ND PASS: DASIWA SCHEDULER",
            "pos": [4770, 5845],
            "size": [260, 110],
            "flags": {},
            "mode": 0,
            "inputs": [
                {
                    "name": "model",
                    "type": "MODEL",
                    "link": None,
                }
            ],
            "outputs": [{"name": "SIGMAS", "type": "SIGMAS", "links": []}],
            "properties": {
                "Node name for S&R": "BasicScheduler",
                "cnr_id": "comfy-core",
            },
            "widgets_values": [
                DASIWA_SECOND_STAGE_SCHEDULER,
                DASIWA_SECOND_STAGE_STEPS,
                DASIWA_SECOND_STAGE_DENOISE,
            ],
        },
    )


def use_tiled_decode(workflow):
    decode = node_by_id(workflow, 254)
    decode["type"] = "VAEDecodeTiled"
    decode["title"] = "TILED DECODE (2X OUTPUT)"
    decode["size"] = [280, 200]
    decode["inputs"] = decode["inputs"][:2] + [
        {
            "name": "tile_size",
            "type": "INT",
            "widget": {"name": "tile_size"},
            "link": None,
        },
        {
            "name": "overlap",
            "type": "INT",
            "widget": {"name": "overlap"},
            "link": None,
        },
        {
            "name": "temporal_size",
            "type": "INT",
            "widget": {"name": "temporal_size"},
            "link": None,
        },
        {
            "name": "temporal_overlap",
            "type": "INT",
            "widget": {"name": "temporal_overlap"},
            "link": None,
        },
    ]
    decode["properties"] = {
        "Node name for S&R": "VAEDecodeTiled",
        "cnr_id": "comfy-core",
    }
    decode["widgets_values"] = [768, 64, 4096, 4]


def apply_dasiwa_hybrid_settings(workflow):
    node_by_id(workflow, 183)["widgets_values"][1] = DASIWA_FIRST_STAGE_MEGAPIXELS
    node_by_id(workflow, 292)["widgets_values"][0] = DASIWA_GUIDE_LONG_EDGE

    distilled_lora = node_by_id(workflow, 322)
    distilled_lora["widgets_values"][1] = DASIWA_DISTILLED_LORA_STRENGTH

    reasoning_lora = node_by_id(workflow, 323)
    reasoning_lora["mode"] = 0
    reasoning_lora["title"] = "DaSiWa Reasoning I2V LoRA"
    reasoning_lora["widgets_values"] = [
        DASIWA_REASONING_LORA,
        DASIWA_REASONING_LORA_STRENGTH,
    ]

    video_combine = node_by_id(workflow, 325)
    video_combine["widgets_values"]["crf"] = DASIWA_VIDEO_CRF
    video_combine["widgets_values"]["filename_prefix"] = "LTX23-DaSiWaHybrid"


def add_second_stage(workflow, *, dasiwa_hybrid=False):
    # A 0.5 MP first pass becomes roughly 2 MP after the x2 spatial upscaler.
    node_by_id(workflow, 183)["widgets_values"][1] = FIRST_STAGE_MEGAPIXELS
    if dasiwa_hybrid:
        apply_dasiwa_hybrid_settings(workflow)

    remove_target_link(workflow, 254, 0)
    remove_target_link(workflow, 255, 0)
    use_tiled_decode(workflow)

    for node_id in (254, 255, 325):
        node_by_id(workflow, node_id)["pos"][0] += 1800
    for node_id in (343, 344):
        if any(node["id"] == node_id for node in workflow["nodes"]):
            node_by_id(workflow, node_id)["pos"][0] += 1800

    upscale_loader = make_upscale_loader(workflow)
    upsampler = make_latent_upsampler(workflow)

    guide_id = new_node_id(workflow)
    guide = clone_node(
        workflow,
        317,
        guide_id,
        [4440, 5588],
        "2ND PASS: RE-APPLY IMAGE GUIDE",
    )
    if guide.get("widgets_values", [None])[0] == "2":
        guide["widgets_values"] = LOOP_SECOND_STAGE_GUIDE_VALUES.copy()
    workflow["nodes"].append(guide)

    guider_id = new_node_id(workflow)
    guider = clone_node(workflow, 284, guider_id, [4770, 5588], "2ND PASS CFG 1")
    guider["widgets_values"] = [1]
    workflow["nodes"].append(guider)

    sampler_select_id = new_node_id(workflow)
    sampler_select = clone_node(
        workflow,
        297,
        sampler_select_id,
        [4770, 5735],
        "2ND PASS SAMPLER",
    )
    sampler_select["widgets_values"] = ["euler_cfg_pp"]
    workflow["nodes"].append(sampler_select)

    if dasiwa_hybrid:
        sigmas_id = make_basic_scheduler(workflow)
    else:
        sigmas_id = make_manual_sigmas(workflow)

    concat_id = new_node_id(workflow)
    concat = clone_node(workflow, 258, concat_id, [4440, 5860], "2ND PASS AV LATENT")
    workflow["nodes"].append(concat)

    sampler_id = new_node_id(workflow)
    sampler = clone_node(
        workflow,
        257,
        sampler_id,
        [5100, 5588],
        "2ND PASS: UPSCALE REFINE",
    )
    workflow["nodes"].append(sampler)

    separate_id = new_node_id(workflow)
    separate = clone_node(
        workflow,
        316,
        separate_id,
        [5405, 5588],
        "2ND PASS AV OUTPUT",
    )
    workflow["nodes"].append(separate)

    crop_id = new_node_id(workflow)
    crop = clone_node(
        workflow,
        315,
        crop_id,
        [5405, 5680],
        "REMOVE 2ND PASS GUIDES",
    )
    workflow["nodes"].append(crop)

    # Crop stage-one guide tokens before latent upscaling.
    add_link(workflow, 315, 2, upsampler, 0, "LATENT")
    add_link(workflow, upscale_loader, 0, upsampler, 1, "LATENT_UPSCALE_MODEL")
    add_link(workflow, 293, 2, upsampler, 2, "VAE")

    # Re-encode the same source guide(s) at the upscaled latent resolution.
    add_link(workflow, 315, 0, guide_id, 0, "CONDITIONING")
    add_link(workflow, 315, 1, guide_id, 1, "CONDITIONING")
    add_link(workflow, 293, 2, guide_id, 2, "VAE")
    add_link(workflow, upsampler, 0, guide_id, 3, "LATENT")
    source_guide = node_by_id(workflow, 317)
    for target_slot in range(4, len(source_guide["inputs"])):
        source_link_id = source_guide["inputs"][target_slot]["link"]
        source_link = next(
            item for item in workflow["links"] if item[0] == source_link_id
        )
        add_link(
            workflow,
            source_link[1],
            source_link[2],
            guide_id,
            target_slot,
            "IMAGE",
        )

    add_link(workflow, 320, 0, guider_id, 0, "MODEL")
    add_link(workflow, guide_id, 0, guider_id, 1, "CONDITIONING")
    add_link(workflow, guide_id, 1, guider_id, 2, "CONDITIONING")

    add_link(workflow, guide_id, 2, concat_id, 0, "LATENT")
    add_link(workflow, 316, 1, concat_id, 1, "LATENT")

    add_link(workflow, 286, 0, sampler_id, 0, "NOISE")
    add_link(workflow, guider_id, 0, sampler_id, 1, "GUIDER")
    add_link(workflow, sampler_select_id, 0, sampler_id, 2, "SAMPLER")
    if dasiwa_hybrid:
        add_link(workflow, 320, 0, sigmas_id, 0, "MODEL")
    add_link(workflow, sigmas_id, 0, sampler_id, 3, "SIGMAS")
    add_link(workflow, concat_id, 0, sampler_id, 4, "LATENT")

    add_link(workflow, sampler_id, 0, separate_id, 0, "LATENT")
    add_link(workflow, guide_id, 0, crop_id, 0, "CONDITIONING")
    add_link(workflow, guide_id, 1, crop_id, 1, "CONDITIONING")
    add_link(workflow, separate_id, 0, crop_id, 2, "LATENT")
    add_link(workflow, crop_id, 2, 254, 0, "LATENT")
    add_link(workflow, separate_id, 1, 255, 0, "LATENT")

    workflow.setdefault("groups", []).append(
        {
            "id": max(group.get("id", 0) for group in workflow.get("groups", []))
            + 1,
            "title": (
                "2nd Pass: DaSiWa-style latent x2 + 4-step refine"
                if dasiwa_hybrid
                else "2nd Pass: Latent x2 + 4-step refine"
            ),
            "bounding": [3825, 5505, 1810, 735],
            "color": "#3f789e",
            "font_size": 24,
            "flags": {},
        }
    )
    return workflow


def render(source_name):
    source = WORKFLOWS / source_name
    workflow = json.loads(source.read_text(encoding="utf-8"))
    return json.dumps(add_second_stage(workflow), ensure_ascii=False, indent=2) + "\n"


def render_dasiwa_hybrid(source_name):
    source = WORKFLOWS / source_name
    workflow = json.loads(source.read_text(encoding="utf-8"))
    return (
        json.dumps(
            add_second_stage(workflow, dasiwa_hybrid=True),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def main():
    for source_name, output_name in TARGETS.items():
        output = WORKFLOWS / output_name
        output.write_text(render(source_name), encoding="utf-8")
        print(f"Wrote {output}")
    for source_name, output_name in DASIWA_HYBRID_TARGETS.items():
        output = WORKFLOWS / output_name
        output.write_text(render_dasiwa_hybrid(source_name), encoding="utf-8")
        print(f"Wrote {output}")


if __name__ == "__main__":
    main()
