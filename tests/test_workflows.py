import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_two_stage_workflows


class WorkflowTests(unittest.TestCase):
    def test_workflows_use_full_checkpoint_vaes_and_save_output(self):
        for path in (ROOT / "workflows").glob("*.json"):
            workflow = json.loads(path.read_text(encoding="utf-8"))
            nodes = {node["id"]: node for node in workflow["nodes"]}
            links = {link[0]: link for link in workflow["links"]}

            checkpoint = nodes[293]
            self.assertEqual(
                checkpoint["widgets_values"][0],
                "10Eros_v1-fp8mixed_learned.safetensors",
            )
            self.assertIn(600, checkpoint["outputs"][2]["links"])
            self.assertIn(651, checkpoint["outputs"][2]["links"])
            self.assertEqual(links[600][1:3], [293, 2])
            self.assertEqual(links[651][1:3], [293, 2])

            audio_vae = nodes[339]
            self.assertEqual(
                audio_vae["widgets_values"][0],
                "10Eros_v1-fp8mixed_learned.safetensors",
            )

            preview = nodes[320]
            preview_vae = next(
                item for item in preview["inputs"] if item["name"] == "vae"
            )
            self.assertIsNone(preview_vae["link"])

            video_combine = nodes[325]
            self.assertTrue(video_combine["widgets_values"]["save_output"])

    def test_loop_guide_strengths_leave_room_for_prompt_and_loras(self):
        workflow = json.loads(
            (
                ROOT
                / "workflows"
                / "video_ltx23_i2v_first_last_same.json"
            ).read_text(encoding="utf-8")
        )
        loop_guide = next(node for node in workflow["nodes"] if node["id"] == 317)
        self.assertEqual(loop_guide["widgets_values"], ["2", 0, 0.9, -1, 0.35])
        links = {link[0]: link for link in workflow["links"]}
        self.assertEqual(links[706][1:5], [254, 0, 343, 0])
        self.assertEqual(links[707][1:5], [343, 0, 344, 1])
        self.assertEqual(links[708][1:5], [344, 0, 325, 0])

    def test_generated_two_stage_workflows_are_current(self):
        for source_name, output_name in generate_two_stage_workflows.TARGETS.items():
            output = ROOT / "workflows" / output_name
            self.assertEqual(
                output.read_text(encoding="utf-8"),
                generate_two_stage_workflows.render(source_name),
            )

    def test_two_stage_workflows_have_complete_graphs(self):
        for output_name in generate_two_stage_workflows.TARGETS.values():
            workflow = json.loads(
                (ROOT / "workflows" / output_name).read_text(encoding="utf-8")
            )
            nodes = {node["id"]: node for node in workflow["nodes"]}
            links = {link[0]: link for link in workflow["links"]}

            for link_id, origin_id, origin_slot, target_id, target_slot, _ in links.values():
                self.assertIn(origin_id, nodes)
                self.assertIn(target_id, nodes)
                self.assertIn(
                    link_id, nodes[origin_id]["outputs"][origin_slot]["links"]
                )
                self.assertEqual(
                    nodes[target_id]["inputs"][target_slot]["link"], link_id
                )

            for node in nodes.values():
                for input_item in node.get("inputs", []):
                    link_id = input_item.get("link")
                    if link_id is not None:
                        self.assertIn(link_id, links)
                for output_item in node.get("outputs", []):
                    for link_id in output_item.get("links") or []:
                        self.assertIn(link_id, links)

            types = [node["type"] for node in nodes.values()]
            self.assertIn("LatentUpscaleModelLoader", types)
            self.assertIn("LTXVLatentUpsampler", types)
            self.assertIn("ManualSigmas", types)
            self.assertIn("VAEDecodeTiled", types)
            self.assertEqual(types.count("SamplerCustomAdvanced"), 2)
            self.assertEqual(types.count("LTXVSeparateAVLatent"), 2)

            sigma_node = next(
                node for node in nodes.values() if node["type"] == "ManualSigmas"
            )
            self.assertEqual(
                sigma_node["widgets_values"][0],
                generate_two_stage_workflows.SECOND_STAGE_SIGMAS,
            )

            upscale_loader = next(
                node
                for node in nodes.values()
                if node["type"] == "LatentUpscaleModelLoader"
            )
            self.assertEqual(
                upscale_loader["widgets_values"][0],
                generate_two_stage_workflows.UPSCALE_MODEL,
            )

            size_node = nodes[183]
            self.assertEqual(
                size_node["widgets_values"][1],
                generate_two_stage_workflows.FIRST_STAGE_MEGAPIXELS,
            )

            if "first_last_same" in output_name:
                second_stage_guide = next(
                    node
                    for node in nodes.values()
                    if node.get("title") == "2ND PASS: RE-APPLY IMAGE GUIDE"
                )
                self.assertEqual(
                    second_stage_guide["widgets_values"],
                    generate_two_stage_workflows.LOOP_SECOND_STAGE_GUIDE_VALUES,
                )
                decoded_to_copy = next(
                    link
                    for link in links.values()
                    if link[1:5] == [254, 0, 343, 0]
                )
                copy_to_replace = next(
                    link
                    for link in links.values()
                    if link[1:5] == [343, 0, 344, 1]
                )
                replace_to_video = next(
                    link
                    for link in links.values()
                    if link[1:5] == [344, 0, 325, 0]
                )
                self.assertIsNotNone(decoded_to_copy)
                self.assertIsNotNone(copy_to_replace)
                self.assertIsNotNone(replace_to_video)

    def test_manifest_contains_two_stage_models(self):
        manifest = json.loads(
            (ROOT / "config" / "ltx-video-models.json").read_text(
                encoding="utf-8"
            )
        )
        paths = {
            model["path"]
            for model in manifest["models"]
            if model.get("enabled", True)
        }
        self.assertIn(
            "models/latent_upscale_models/"
            + generate_two_stage_workflows.UPSCALE_MODEL,
            paths,
        )
        self.assertNotIn("models/vae/LTX23_video_vae_bf16.safetensors", paths)
        self.assertNotIn("models/vae/LTX23_audio_vae_bf16.safetensors", paths)

    def test_custom_nodes_are_pinned(self):
        lines = (ROOT / "custom_nodes.txt").read_text(
            encoding="utf-8"
        ).splitlines()
        for line in lines:
            if not line or line.startswith("#"):
                continue
            name, url, revision = line.split("|")
            self.assertTrue(name)
            self.assertTrue(url.startswith("https://github.com/"))
            self.assertRegex(revision, r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
