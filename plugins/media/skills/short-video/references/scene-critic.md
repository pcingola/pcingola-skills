# Stills critic: one review of an HTML scene

The agent that builds an HTML scene (or a world) does not judge its own
stills. Once the scene passes the motion check, one critic that saw none of
the work reviews its stills, once, through the eyes of the film's audience.
`references/critic.md` is a different review (the scene critic of
`critic.claude` and the film critic): stillness, facts, narration and sound.

## The review

1. Take the stills: `stills --scene ID --sheet --at <times>` at one per
   second and at every time the Brief names (a world: per scene; one critic
   reviews the stills of all the world's scenes, once). Keep the full-size
   PNGs and the sheet.
2. Look for `stills/critic.md` in every version of the scene
   (`scenes/<id>/v*/`, a world: `worlds/<name>/v*/`). If one exists, the
   scene has had its review: spawn no critic. Otherwise have a fresh critic
   review the stills, a new subagent with no part in the scene. An agent with the Agent tool spawns it. A scene subagent without
   the Agent tool does not review its own stills: it reports the scene done
   to the main agent with the paths of the stills, and the main agent spawns
   the critic and hands the findings back to that subagent (SendMessage) or
   fixes them itself. Give the critic:
   - the absolute paths of the sheet and the full-size stills;
   - the scene's Brief, and the reference stills the Brief names (`refs/...`)
     when the film has a reference;
   - the storyboard file (its `Topic:` names the audience) and `lessons.md`
     (the user's corrections so far);
   - `critic.scene_max_findings` of `settings.yaml`;
   - the prompt below.
   Give it no reasoning, plan, page code or notes of yours.
3. Save its reply as `stills/critic.md` in the version directory.
4. Fix each finding you agree with, run `check`, and take the stills again
   to confirm the fixes and the motion check. Decline a finding you
   disagree with, with one line saying why, appended to `stills/critic.md`.
5. The review is done. No second critic reviews the scene, whatever the
   fixes were; the scene goes to the user. A later edit of the scene (a
   user's correction, a new voice) gets no new critic review, only the
   motion check.

## Prompt for the critic

    You review stills of one scene of an animated film. You did not make
    it. Open every file listed. Read the storyboard's Topic: it names the
    film's audience. Judge everything as a viewer from that audience who
    watches the film once, at full speed, without pausing. lessons.md lists
    corrections the film's author has already made: they show what the
    author notices and cares about.

    First, look at the contact sheet as a whole and write one sentence: does
    this scene work for this audience, and if not, why not.

    Then list the problems that viewer would notice on that one viewing and
    that would change what they understand (confusing, misleading, wrong,
    unreadable) or make the film look amateur to them. For each problem the
    answer to both questions must be yes: would the viewer notice it, and
    would it matter to them. Small differences in alignment, shade or weight
    that the viewer would not notice are not problems. Examples of problems:
    text cut off or too small to read, a number that disagrees with the
    narration or between stills, a black or blank frame, objects fused or
    the camera inside an object, a frame so empty or cluttered that the
    subject is lost, a look far from the Brief or the reference stills.
    These are examples; report any problem that passes the test.

    Report at most <critic.scene_max_findings> problems, the most harmful
    first. "none" is a valid answer and is expected for a scene that works.

    Reply as:
    verdict: one sentence
    problems: one numbered line each, or "none". Each line gives the still
    (file and time), what the viewer would get wrong or why it makes the
    film look amateur to them, and a concrete fix ("raise the label to 48 px and move it left of the crane",
    not "improve the label").
