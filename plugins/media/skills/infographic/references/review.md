# Independent review

The maker sees what it meant to show. A reviewer that has not seen the maker's
notes or the intended concept sees what is there. The review judges, in this
order: whether the image is easy to understand, whether it is beautiful, then
whether it is correct. An accurate image that fails the first two will not be
read.

## Reviewers

- A cold reader: a subagent (Agent tool) given only the image, not the
  sources, the prompt or the intended concept. It answers the cold-read
  questions below.
- A full reviewer: a subagent given the image, the prompt and the source files,
  with the whole checklist below as its brief.
- A second opinion from a model that is not Claude: load `ai:second-opinion`
  and ask for a review of the image (and the sources, when they are text or
  PDF) with the checklist below as the brief. Skip it when the user asks to.

Reviewers report findings and do not edit. Verify each finding against the
image and the sources before acting on it; reviewers also report defects that
are not there.

## Cold read

1. In one sentence, what does this image explain?
2. Where did your eye go first, and in what order did you look at the rest?
3. What did you not understand, or have to look at twice?
4. What would you remove?

The image passes when the answer to 1 matches the intended concept and the
order in 2 follows the story. A mismatch is a finding about the design, fixed in
the image, not explained in a caption.

## Checklist

1. Comprehension: the concept is clear from the title, subtitle and main
   picture within a few seconds; one entry point; reading order follows the
   story; no element whose purpose is unclear; one concept only.
2. Infographic, not diagram: the picture shows the thing itself; no rows of
   boxes joined by arrows, no cards of bullet points.
3. Appearance: whether someone would stop to look at it. Hierarchy, balance of
   filled and empty areas, palette harmony, typography, one consistent style;
   anything that looks crowded, generic or dated. Name the defect and where it
   is, and propose a concrete change.
4. Text: every word and number spelt as in the prompt, no extra text the prompt
   did not ask for, labels placed on the part they name, abbreviations
   expanded, one name per system.
5. Facts against the sources: every statement, number, name and status word is
   in a source, with the source's wording; drawn proportions match the numbers;
   no path or journey shows a movement the sources describe as planned, partial
   or absent.
6. Omissions: anything in the sources that the concept needs and the image
   leaves out.

## Rounds

Fix what the verified findings show, generate the next version and review
again, with a new cold reader each round (one that has seen an earlier version
is no longer cold). Stop when a round finds nothing, or after three rounds, and
report what is still open.
