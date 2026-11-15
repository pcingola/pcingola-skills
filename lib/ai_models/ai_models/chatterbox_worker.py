"""Chatterbox Turbo worker, run by `chatterbox` with the interpreter of the provider's environment:

    <python> -I chatterbox_worker.py <weights dir>

It imports nothing of `ai_models`. It loads the model on the CPU, writes one JSON line `{"ready": true}` and then
answers each JSON request line on stdin, `{"text", "reference", "out"}`, by writing a 16-bit WAV file to `out` and
one JSON line `{"ok": true}` or `{"error": "<message>"}`. `reference` is null (the model's built-in voice) or the
path of a recording longer than `MIN_REFERENCE_SECONDS`. The protocol uses a copy of stdout; the process's stdout
goes to stderr, so library prints do not reach the caller as answers.
"""

import json
import os
import sys

MIN_REFERENCE_SECONDS = 5.0


def main() -> None:
    answers = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # the weights are local; no request to huggingface.co
    import numpy as np
    import soundfile as sf
    from chatterbox.tts_turbo import ChatterboxTurboTTS

    tts = ChatterboxTurboTTS.from_local(sys.argv[1], "cpu")
    # Under numpy 2 the loudness gain (a float64 scalar) promotes the float32 reference to float64, which the mel
    # filter matmul rejects.
    norm = tts.norm_loudness
    tts.norm_loudness = lambda wav, sr, target_lufs=-27: np.asarray(norm(wav, sr, target_lufs), dtype=np.float32)
    builtin, current = tts.conds, None
    answers.write(json.dumps({"ready": True}) + "\n")
    for line in sys.stdin:
        req = json.loads(line)
        try:
            ref = req.get("reference")
            if ref != current:
                if ref is None:
                    tts.conds = builtin
                else:
                    seconds = sf.info(ref).duration
                    if seconds <= MIN_REFERENCE_SECONDS:
                        raise ValueError(f"{ref}: {seconds:.1f} s; a reference must be longer than "
                                         f"{MIN_REFERENCE_SECONDS:g} s")
                    tts.prepare_conditionals(ref)
                current = ref
            audio = tts.generate(req["text"]).detach().cpu().numpy().reshape(-1)
            sf.write(req["out"], audio, int(getattr(tts, "sr", 24_000)), subtype="PCM_16")
            answers.write(json.dumps({"ok": True}) + "\n")
        except Exception as e:  # noqa: BLE001 - every failure goes back to the caller as one answer
            answers.write(json.dumps({"error": f"{type(e).__name__}: {e}"}) + "\n")


if __name__ == "__main__":
    main()
