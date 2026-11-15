"""The prompt that carries one comment from the editor page to the agent."""

from __future__ import annotations

from pathlib import Path

from .comment import Comment

SKILL = "media:html-animation"
POST_TOOL = "mcp__media__post"
NOTE_TOOL = "mcp__media__note"


def comment_prompt(comment: Comment, folder: Path) -> str:
    """The full prompt text of the `request` line."""
    ids = ", ".join(f"`{i}`" for i in comment.ids) if comment.ids else "none (the mark is on the background)"
    chapter = f"`{comment.chapter}`" if comment.chapter else "unknown"
    return (
        f"A comment from the HTML animation editor page. Load `{SKILL}` with the Skill tool and handle the "
        "comment as that skill says.\n\n"
        f"- Animation folder: `{folder}`\n"
        f"- Comment id: `{comment.id}`\n"
        f"- Time: t = {comment.t:.3f} s\n"
        f"- Chapter: {chapter}\n"
        f"- Mark: {comment.mark.describe()}\n"
        f"- Element ids under the mark (innermost first): {ids}\n"
        f"- Frame at t with the mark drawn in red: `{comment.png}`\n\n"
        "The user's message:\n\n"
        f"{comment.message}\n\n"
        "Run `snapshot` on the folder immediately before your first edit, so this comment's change can be undone. "
        "Change only the chapter and the elements the comment names, then run `build` and `validate`; the page "
        "reloads at the same t when `index.html` changes. "
        f"Answer the user in the editor page with the `post` tool (`{POST_TOOL}`), and report progress there "
        f"with the `note` tool (`{NOTE_TOOL}`)."
    )
