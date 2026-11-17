"""A tiny ACE-Step pipeline with random weights, for the music tests.

The components follow the dummy components of diffusers' own ACE-Step pipeline test (v0.43.0,
`tests/pipelines/ace_step/test_ace_step.py`): hidden size 32, 2 layers. The VAE differs: it decodes at 48 kHz with a
hop of 1920 samples (25 latents per second, as the released model), so the output is a playable stereo track that
FFmpeg encodes to MP3. The tokenizer is the one of the released text encoder, Qwen3-Embedding-0.6B (downloaded once
by `build`).
"""

from __future__ import annotations

from pathlib import Path

TOKENIZER_REPO = "Qwen/Qwen3-Embedding-0.6B"

# The attention sizes every transformer component of the tiny pipeline shares.
_ATTENTION = {"num_attention_heads": 4, "num_key_value_heads": 2, "head_dim": 8}
_LAYER = {"hidden_size": 32, "intermediate_size": 64, **_ATTENTION}
_WINDOW = {"rope_theta": 10000.0, "sliding_window": 16}


def build(path: Path) -> Path:
    """Write the tiny ACE-Step pipeline to the folder `path` with `save_pretrained`; return `path`."""
    import torch
    from diffusers import AceStepConditionEncoder, AutoencoderOobleck, FlowMatchEulerDiscreteScheduler
    from diffusers.models.transformers.ace_step_transformer import AceStepTransformer1DModel
    from diffusers.pipelines.ace_step import AceStepAudioTokenDetokenizer, AceStepAudioTokenizer, AceStepPipeline
    from transformers import AutoTokenizer, Qwen3Config, Qwen3Model

    torch.manual_seed(0)
    transformer = AceStepTransformer1DModel(**_LAYER, **_WINDOW, num_hidden_layers=2, in_channels=24,
                                            audio_acoustic_hidden_dim=8, patch_size=2)
    text_encoder = Qwen3Model(Qwen3Config(**_LAYER, num_hidden_layers=2, vocab_size=151936,
                                          max_position_embeddings=256))
    condition_encoder = AceStepConditionEncoder(**_LAYER, **_WINDOW, text_hidden_dim=32, timbre_hidden_dim=8,
                                                num_lyric_encoder_hidden_layers=2,
                                                num_timbre_encoder_hidden_layers=2)
    audio_tokenizer = AceStepAudioTokenizer(**_LAYER, **_WINDOW, audio_acoustic_hidden_dim=8, pool_window_size=2,
                                            fsq_dim=32, fsq_input_levels=[4, 4, 4], fsq_input_num_quantizers=1,
                                            num_attention_pooler_hidden_layers=1)
    audio_token_detokenizer = AceStepAudioTokenDetokenizer(**_LAYER, **_WINDOW, audio_acoustic_hidden_dim=8,
                                                           pool_window_size=2, num_attention_pooler_hidden_layers=1)
    vae = AutoencoderOobleck(encoder_hidden_size=6, downsampling_ratios=[32, 60], decoder_channels=3,
                             decoder_input_channels=8, audio_channels=2, channel_multiples=[2, 4],
                             sampling_rate=48000)
    pipe = AceStepPipeline(vae=vae, text_encoder=text_encoder, tokenizer=AutoTokenizer.from_pretrained(TOKENIZER_REPO),
                           transformer=transformer, condition_encoder=condition_encoder,
                           scheduler=FlowMatchEulerDiscreteScheduler(num_train_timesteps=1, shift=1.0),
                           audio_tokenizer=audio_tokenizer, audio_token_detokenizer=audio_token_detokenizer)
    pipe.save_pretrained(path)
    return path
