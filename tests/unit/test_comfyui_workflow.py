"""Unit tests for packages.visual_pipeline.comfyui — build_comfyui_workflow."""

import pytest

from packages.visual_pipeline.comfyui import build_comfyui_workflow


@pytest.mark.unit
class TestBuildComfyuiWorkflow:
    """Tests for build_comfyui_workflow() workflow dict construction."""

    def test_returns_dict_with_required_node_keys(self):
        wf = build_comfyui_workflow("test prompt", "model.safetensors")
        for key in ("3", "4", "5", "6", "7", "8", "9"):
            assert key in wf, f"Missing node key '{key}' in workflow"

    def test_ksampler_has_correct_params(self):
        wf = build_comfyui_workflow(
            "test prompt", "model.safetensors",
            steps=30, cfg_scale=9.0, sampler="euler", scheduler="normal",
        )
        ks = wf["3"]["inputs"]
        assert ks["steps"] == 30
        assert ks["cfg"] == 9.0
        assert ks["sampler_name"] == "euler"
        assert ks["scheduler"] == "normal"
        assert wf["3"]["class_type"] == "KSampler"

    def test_checkpoint_loader_has_correct_model(self):
        wf = build_comfyui_workflow("p", "realcartoonPixar_v12.safetensors")
        assert wf["4"]["inputs"]["ckpt_name"] == "realcartoonPixar_v12.safetensors"
        assert wf["4"]["class_type"] == "CheckpointLoaderSimple"

    def test_empty_latent_image_dimensions(self):
        wf = build_comfyui_workflow("p", "m.safetensors", width=640, height=960)
        latent = wf["5"]["inputs"]
        assert latent["width"] == 640
        assert latent["height"] == 960
        assert wf["5"]["class_type"] == "EmptyLatentImage"

    def test_positive_prompt_matches_design_prompt(self):
        wf = build_comfyui_workflow("beautiful sunset over mountains", "m.safetensors")
        assert wf["6"]["inputs"]["text"] == "beautiful sunset over mountains"
        assert wf["6"]["class_type"] == "CLIPTextEncode"

    def test_negative_prompt_matches_input(self):
        neg = "ugly, deformed, extra limbs"
        wf = build_comfyui_workflow("p", "m.safetensors", negative_prompt=neg)
        assert wf["7"]["inputs"]["text"] == neg
        assert wf["7"]["class_type"] == "CLIPTextEncode"

    def test_explicit_seed_used_in_ksampler(self):
        wf = build_comfyui_workflow("p", "m.safetensors", seed=42)
        assert wf["3"]["inputs"]["seed"] == 42

    def test_none_seed_generates_random_int(self):
        wf = build_comfyui_workflow("p", "m.safetensors", seed=None)
        seed_val = wf["3"]["inputs"]["seed"]
        assert isinstance(seed_val, int)
        assert seed_val >= 1

    def test_video_generation_type_produces_vhs_node(self):
        wf = build_comfyui_workflow(
            "p", "m.safetensors", generation_type="video", width=1024, height=1024,
        )
        assert wf["9"]["class_type"] == "VHS_VideoCombine"
        # Video mode caps dimensions at 768
        assert wf["5"]["inputs"]["width"] <= 768
        assert wf["5"]["inputs"]["height"] <= 768
        # Batch size should be 16 for video
        assert wf["5"]["inputs"]["batch_size"] == 16
