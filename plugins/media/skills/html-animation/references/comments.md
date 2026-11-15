# Editor comments

The editor page (`/animate <folder>`) sends each comment as a prompt. It holds:

- the animation folder;
- the comment id;
- `t` in seconds and the chapter id;
- the mark: a point or a rectangle in stage pixels;
- the element ids under the mark, innermost first (none when the mark is on the background);
- the PNG of the frame at `t` with the mark in red;
- the user's message.

## Steps

1. Read the PNG. The red ring or rectangle is the mark, drawn by the editor; it is not part of the animation.
2. Run `snapshot <folder>` immediately before the first edit. The editor takes no snapshot itself: a comment
   queued behind another starts from that comment's result, so the snapshot is taken when the work starts.
3. Read `animation.json`, `content.json` and the named chapter's html and js.
4. Find what the message is about: the innermost id that fits it, else an outer one; a mark on the background is
   about the chapter as a whole. The time `t` places the change on the chapter's timeline: local time is `t` minus
   the chapter's start (the sum of the durations before it).
5. Change only the named chapter and the elements the message is about, in the file that owns them:
   - text, numbers, colours: `content.json`;
   - layout and static style: `chapters/<id>.html`;
   - motion, timing, easing: `chapters/<id>.js`;
   - chapter length or title: `animation.json`.
   Keep every other element, id and timing as it is. An id the editor reported stays, so later comments still find
   the element.
6. `build`, then `validate`; fix errors until `ok` is true. The editor reloads at the same `t` when `index.html`
   changes.
7. `still <folder> --at <t>` and Read the PNG to check the change at the commented time.
8. Answer with the `post` tool the prompt names: what changed, in one to three sentences. Use the `note` tool for
   progress on a change that takes more than one build. If the message asks for something the animation cannot do
   (sound, a file outside the folder), say so in the post and change nothing.

A message that asks about the animation without asking for a change gets an answer in the post and no edit.
