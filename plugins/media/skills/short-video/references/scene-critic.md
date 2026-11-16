# Stills critic: the stopping rule of an HTML scene

The agent that builds an HTML scene (or a world) does not judge its own
stills. After each round of fixes, a critic that saw none of the work scores
the stills, and the agent stops only on the critic's scores. This critic
judges the picture. `references/critic.md` is a different review (the scene
critic of `critic.claude` and the film critic): stillness, facts, narration
and sound.

## The loop

1. Take the stills: `stills --scene ID --sheet --at <times>` at one per
   second and at every time the Brief names (a world: per scene). Keep the
   full-size PNGs and the sheet.
2. Spawn a fresh critic with the Agent tool, a new subagent each round
   (never a continued one). Give it only:
   - the absolute paths of the sheet and the full-size stills of this round;
   - the reference stills the Brief names (`refs/...`), or, when the film has
     no reference, the scene's Brief text;
   - the prompt below.
   Give it no reasoning, plan, page code, earlier scores or notes of yours.
3. Save its reply as `stills/critic_r<N>.md` in the version directory.
4. Fix the five fixes and every defect in the page, check it, take the
   stills again. That is one round.
5. Stop when every score is 7 or more and no defect remains, or after round
   5 (or the lower round limit the caller gives). After the last round,
   report the scores that stay below 7 and the defects left to the user. A scene that fails the motion check is not done in any
   case.

The agent does not overrule a score below 7: it fixes the page, or changes
the scene's method.

## Prompt for the critic

    You review stills of one scene of an animated film. You did not make
    it. Open every file listed. The film is to match the reference stills
    (or, without reference stills, the Brief) in look and quality. Its
    audience: <the audience the storyboard's Topic names>.

    Score each criterion from 1 to 10. 5 is an amateur draft, 7 is a
    competent professional motion piece, 9 is the reference's level or
    better. For each score give the evidence: the still (file and time)
    and what in it earns or costs the score.

    1. Craft: modelling, materials, edges, anti-aliasing, finish.
    2. 3D world density and detail: ground, buildings, vehicles,
       vegetation, props; share of the frame that is empty.
    3. Light and colour: value contrast (darkest to lightest), light
       sources, shadows, palette against the reference.
    4. Camera and composition: framing, subject size, horizon, focus,
       depth of field, the path between stills.
    5. Typography and overlays: font, size, contrast, placement, alignment.
    6. Story legibility: whether a viewer with no narration understands
       what each still shows and what changed.
    7. Defects: objects fused or intersecting, the camera inside or
       grazing geometry, clipped or cut-off text, numbers that disagree
       between stills, z-fighting, black or blank frames, stray artefacts.
       Score 10 with no defect; list every defect with its still.

    Then list the top five fixes, most harmful first. Each fix names the
    still, the element and a concrete change with numbers where possible
    ("raise the quay lights to 3x and add 40 lit windows on the warehouses
    left of the crane", not "improve lighting").

    Reply as:
    scores: craft N, density N, light N, camera N, type N, story N, defects N
    evidence: one line per criterion
    defects: one line each, or "none"
    fixes: five numbered lines

## Without the Agent tool

An agent that cannot spawn a subagent (it is itself one) is its own critic,
in a separate step:

1. Before looking at the stills of the round, write
   `stills/checklist_r<N>.md`: for each of the seven criteria, the checks a
   7 needs in this scene, stated as facts to verify in a still (for a night
   scene: "sky darker than every lit object", "at least 20 lit points",
   "a shadow under each crane"). Take them from the reference stills or the
   Brief and `references/three.md`, "Craft".
2. Then open the stills and answer each check with yes or no and the still
   that shows it. A criterion scores at most 6 while one of its checks is
   no.
3. Save the scores, defects and top five fixes in the format above as
   `stills/critic_r<N>.md`, and continue the loop at step 4.
