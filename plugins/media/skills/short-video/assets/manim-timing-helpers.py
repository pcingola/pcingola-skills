
import re

from manim import Scene, config

DURATION = TIMING["duration"]


def norm(s):
    """Lowercase letters and digits only, as `norm` in timing.js."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _sentence(n):
    for s in TIMING["sentences"]:
        if s["index"] == n:
            return s
    raise ValueError(f"sv_timing.py: no sentence {n} (scene has {len(TIMING['sentences'])})")


def _word(n, w, k=1):
    s, want, seen = _sentence(n), norm(w), 0
    for word in s["words"]:
        if norm(word["text"]) == want:
            seen += 1
            if seen == k:
                return word
    raise ValueError(f'sv_timing.py: word "{w}" #{k} not in sentence {n}: {s["text"]}')


def S(n):
    """Start of sentence n (1-based), in seconds of scene time."""
    return _sentence(n)["start"]


def SE(n):
    """End of sentence n."""
    return _sentence(n)["end"]


def W(n, word, k=1):
    """Start of the k-th occurrence of `word` in sentence n (case and punctuation ignored)."""
    return _word(n, word, k)["start"]


def WE(n, word, k=1):
    """End of the k-th occurrence of `word` in sentence n."""
    return _word(n, word, k)["end"]


class TimedScene(Scene):
    """A Scene that waits for narration times.

    Manim renders whole frames, so scene time moves in steps of 1/fps:
    `self.play(..., run_time=r)` takes ceil(r * fps) frames. `at(t)` and
    `finish()` count in frames: a time is taken at its nearest frame.
    """

    def _static_wait(self):
        # Manim's own test (Scene.should_update_mobjects): a wait with no
        # updaters renders int(duration * fps) frames of one still image;
        # otherwise one frame per started 1/fps.
        return not (self.always_update_mobjects or self.updaters
                    or any(m.has_time_based_updater() for m in self.get_mobject_family_members()))

    def at(self, t):
        """Wait until scene time t (its nearest frame). Nothing happens when
        the scene is at that frame or one frame past it. More than one frame
        past means an animation ran over its cue: ValueError."""
        fps = config.frame_rate
        target, now = round(t * fps), round(self.time * fps)
        if now > target + 1:
            raise ValueError(
                f"at({t:.3f}): the scene is already at {self.time:.3f} s, {now - target} frames past it; "
                "end the animation before it earlier or make it shorter")
        if now >= target:
            return
        n = target - now
        if self._static_wait():
            self.wait((n + 0.5) / fps)
        else:
            self.wait(max(n - 0.5, 1) / fps)
        if round(self.time * fps) != target:
            raise RuntimeError(f"at({t:.3f}): Manim stopped at {self.time:.3f} s, not at frame {target}")

    def finish(self):
        """Wait until the end of the narration (DURATION). The last call of
        `construct`: the rendered video must be as long as the narration.
        The scene ends on the frame nearest to DURATION; a scene already past
        that frame raises ValueError (no grace frame, unlike `at`)."""
        fps = config.frame_rate
        end, now = round(DURATION * fps), round(self.time * fps)
        if now > end:
            raise ValueError(
                f"finish(): the scene is at {self.time:.3f} s (frame {now}), {now - end} frame(s) past the "
                f"end of the narration ({DURATION:.3f} s, frame {end}); shorten or remove the animations "
                "at the end")
        self.at(DURATION)
