"""A tiny Fish Audio Drama 3 checkpoint (`FishOmniModel`) with random weights, for the Fish integration test.

`build` scales down the `config.json` of the Drama 3 repository named in tests/models/config.yaml: hidden size 128,
four backbone layers (three linear-attention layers and one full-attention layer, as the real pattern), four FP8
experts of 128 rows (the FP8 kernels take blocks of 128 by 128), one shared tower layer. The tokenizer, the codebook
counts and the token ids stay those of the real model, so fish-speech builds its prompts unchanged. The codec has a
fixed architecture in fish-speech (`load_codec_model`), so the checkpoint links the real `codec.pth` (1.9 GB) of the
Hugging Face cache. The weights are written in the real checkpoint's tensor names, from the shapes of fish-speech's
own modules. The end-of-speech row of `lm_head` is zero: its logit stays near the middle of the main-token logits,
outside the top-k, so the model speaks until the frame cap.
"""

from __future__ import annotations

import json
from pathlib import Path

# The sizes `build` puts into the real config.json.
TEXT = {
    "hidden_size": 128,
    "intermediate_size": 128,
    "num_hidden_layers": 4,
    "layer_types": ["linear_attention"] * 3 + ["full_attention"],
    "mlp_layer_types": ["moe"] * 4,
    "num_attention_heads": 2,
    "num_key_value_heads": 1,
    "head_dim": 64,
    "linear_key_head_dim": 32,
    "linear_value_head_dim": 32,
    "linear_num_key_heads": 1,
    "linear_num_value_heads": 2,
    "num_experts": 4,
    "num_experts_per_tok": 2,
    "moe_intermediate_size": 128,
    "shared_expert_intermediate_size": 128,
}
TOWER = {
    "dim": 128,
    "text_dim": 128,
    "intermediate_size": 256,
    "n_head": 2,
    "n_local_heads": 1,
    "head_dim": 64,
    "n_layer": 1,
    "shared_enrichment_layers": 1,
}
STD = 0.02  # standard deviation of the random weights
BACKBONE_PREFIX = "model.language_model."  # the backbone's names in the checkpoint start with this, not `model.`
EXPERT_PROJECTIONS = {"w13": ("gate_proj", "up_proj"), "w2": ("down_proj",)}


def scaled(config: dict) -> dict:
    """`config` (a Drama 3 config.json) with the sizes of TEXT and TOWER."""
    return {**config, "text_config": {**config["text_config"], **TEXT},
            "audio_decoder_config": {**config["audio_decoder_config"], **TOWER}}


def _backbone_tensors(model, eos: int, generator) -> dict:
    """Random checkpoint tensors of the backbone `model` (`FishOmniBackbone`): FP8 experts as one weight and block
    scale per expert and projection, the rest in its own dtype; the `lm_head` row of `eos` is zero."""
    import torch
    from fish_speech.models.text2semantic.fish_omni.fp8_moe import FP8_BLOCK_SIZE, FP8_DTYPE

    out = {}
    for name, t in [*model.named_parameters(), *model.named_buffers()]:
        stem, _, kind = name.rpartition(".")
        if stem.endswith(".mlp.experts"):
            if kind.endswith("_scale_inv"):
                continue
            projections = EXPERT_PROJECTIONS[kind.removesuffix("_weight")]
            rows = t.shape[1] // len(projections)
            key = BACKBONE_PREFIX + stem.removeprefix("model.")
            for e in range(t.shape[0]):
                for p in projections:
                    out[f"{key}.{e}.{p}.weight"] = torch.randn(rows, t.shape[2], generator=generator).to(FP8_DTYPE)
                    out[f"{key}.{e}.{p}.weight_scale_inv"] = torch.full(
                        (rows // FP8_BLOCK_SIZE, t.shape[2] // FP8_BLOCK_SIZE), STD)
            continue
        value = (torch.randn(t.shape, generator=generator) * STD).to(t.dtype)
        if name == "lm_head.weight":
            value[eos] = 0
            out[name] = value
        else:
            out[BACKBONE_PREFIX + name.removeprefix("model.")] = value
    return out


def _tower_tensors(model, generator) -> dict:
    """Random checkpoint tensors of the tower `model` (`FishOmniAudioDecoder`)."""
    import torch
    from fish_speech.models.text2semantic.fish_omni.tower import TOWER_CHECKPOINT_PREFIXES

    prefixes = {new: old for old, new in TOWER_CHECKPOINT_PREFIXES.items()}
    out = {}
    for name, t in model.named_parameters():
        new = next(p for p in prefixes if name.startswith(p))
        out[prefixes[new] + name.removeprefix(new)] = (torch.randn(t.shape, generator=generator) * STD).to(t.dtype)
    return out


def build(path: Path, repo: str) -> Path:
    """Write the tiny checkpoint of the Drama 3 repository `repo` to the folder `path`; return `path`."""
    import torch
    from fish_speech.models.text2semantic.fish_omni.backbone import FishOmniBackbone
    from fish_speech.models.text2semantic.fish_omni.config import FishOmniConfig
    from fish_speech.models.text2semantic.fish_omni.tower import FishOmniAudioDecoder
    from huggingface_hub import hf_hub_download
    from safetensors.torch import save_file

    config = scaled(json.loads(Path(hf_hub_download(repo, "config.json")).read_text(encoding="utf-8")))
    (path / "config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
    (path / "tokenizer.json").write_bytes(Path(hf_hub_download(repo, "tokenizer.json")).read_bytes())
    (path / "codec.pth").symlink_to(Path(hf_hub_download(repo, "codec.pth")).resolve())
    parsed = FishOmniConfig.from_dict(config)
    generator = torch.Generator().manual_seed(0)
    with torch.device("cpu"):
        backbone = FishOmniBackbone(parsed.text, fp8_experts=True, dtype=torch.bfloat16)
        tower = FishOmniAudioDecoder(parsed, dtype=torch.bfloat16)
    save_file({**_backbone_tensors(backbone, parsed.eos_token_id, generator), **_tower_tensors(tower, generator)},
              str(path / "model.safetensors"))
    return path
