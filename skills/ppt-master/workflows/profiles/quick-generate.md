---
description: Axion's compact one-pass Generate profile for direct SVG authoring, mechanical delivery, and native PPTX visual review.
---

# Quick Generate Profile

This file is the complete runtime authority for an ordinary Axion Quick run.
It deliberately folds the fork's operational rules into the upstream workflow
instead of appending a second prompt in `ppt-main.yaml`.

**Trigger**: ordinary Generate and Beautify requests select this profile by
default. Use Guided Default only when [`routing.md`](../routing.md) identifies
an explicit escalation trigger.

## 1. Load and execution boundary

- Retain the absolute directory containing `SKILL.md` as `SKILL_DIR` and use
  absolute paths in every command.
- After routing selects this profile, do not read `generate-pptx.md`, role
  prompts, visual-style indexes, mode indexes, chart/table catalogs, preset
  vocabularies, or the large shared reference set. The authoring rules needed
  by ordinary Quick are restated below.
- Load another document only for an explicit feature in this table. Do not load
  it merely because the capability exists.

| Explicit feature | Additional authority |
|---|---|
| Page-image reconstruction | [`image-to-pptx.md`](./image-to-pptx.md) |
| Exact template workspace root | [`apply-template-workspace.md`](../stages/apply-template-workspace.md); apply all contributed Brand/Style/Layout/Deck specs atomically, at most one per kind, with Layout taking structural precedence over Deck |
| Speaker notes | [`executor-notes.md`](../../references/executor-notes.md) |
| Object-level animation | [`customize-animations.md`](../stages/customize-animations.md) |
| Narrated audio/video | [`generate-audio.md`](../stages/generate-audio.md) |

For an ordinary editable deck, keep design decisions in the active context. Do
not create `design_spec.md`, `spec_lock.md`, confirmation payloads, HTML
selectors, or a parallel design contract. A bounded long-source brief under
§2 is source preprocessing, not route state. Do not delegate page authoring and
do not use a script to generate the SVG roster.

## 2. One-pass preparation

Resolve the page count, audience, purpose, canvas, language, source constraints,
and requested deliverables from the request. Make reasonable missing choices
without asking. Quick has no confirmation gate.

Initialize exactly once before extended research or design work:

```bash
python3 ${SKILL_DIR}/scripts/project_manager.py init <short-project-name> \
  --format <format> --quick-generate
```

Use the returned absolute path as `PPT_PROJECT_DIR` for every later read, write,
and command. Do not initialize a replacement project if a later step fails.

### Sources and facts

- Before opening local text, inspect file sizes without loading contents. A
  readable source set is long when any converted/direct text file exceeds
  48 KiB or their aggregate exceeds 96 KiB. Page count does not change this
  threshold.
- For a long source set, create exactly one
  `<PPT_PROJECT_DIR>/analysis/source-brief.md` before page planning. When the
  current registered subagents include a dedicated source-brief worker,
  delegate this intake exactly once; pass only absolute input paths, exact page
  count, audience, purpose, explicit core message, delivery context, artifact
  afterlife, constraints, and the output path. Omit unspecified optional fields
  instead of guessing them. Do not paste source bodies into the goal and do not
  search for another worker. Without that registered worker, produce the same
  artifact in one bounded intake pass.
- The source brief must be sufficient for page authoring without rereading the
  full sources. It contains: the communication target; deck thesis and narrative
  spine; a coverage map from every explicit purpose/constraint and major source
  theme to pages or explicit exclusions; and an exact-page-count outline. Every
  page row includes its role, working title, primary claim, audience move,
  directly usable visible content, evidence locators, semantic relationships,
  rhythm, primary carrier, source qualifiers, and material objections.
- Preserve complete execution payloads for source-backed carriers: chart series
  with labels, units, periods, denominator, and comparison baseline; table row
  and column keys plus material cells; qualitative order/link/hierarchy/
  membership/contrast/overlap; exact equations and links; and source image,
  logo, or diagram paths/URLs with identity, caption, use, and provenance.
  Distinguish facts, source opinions, computations/inferences, scenarios, and
  unknowns. Its character limit is
  `max(6000, min(18000, 3000 + 1100 × page_count))`.
- The brief is a traceable source compression and page-content substrate, not a
  Design Spec, visual contract, immutable final script, or permission to invent
  facts. It may recommend the information-model-fit carrier, but it does not
  prescribe SVG geometry, fonts, colors, or a local authoring capability.
- After the brief exists, read it instead of the full long sources. Reopen raw
  material only for bounded checks of a named claim or locator; never load the
  whole source into the parent authoring context. Short sources may be read as
  supplied.
- Convert Office/PDF/HTML/EPUB/LaTeX/RST inputs once with
  `python3 ${SKILL_DIR}/scripts/source_to_md.py <input...>`, then read only the
  resulting text paths needed by the long/short rule above.
- For a topic-only request or a real fact gap, use `web_search` and `web_fetch`
  directly. Use at most four focused searches and retain no more than five
  authoritative sources unless the user asks for deeper research. Write a
  concise Markdown fact sheet and a compact JSON provenance file under the
  project. Do not load a research runbook.
- Never invent externally verifiable numbers. If a requested business value is
  unknown, label it as an assumption, target, scenario, or formula rather than
  a measured fact.

### Images and icons

Visual variety is a quality decision, not a quota. A management or analytical
deck may use native shapes, diagrams, and charts throughout when they carry the
message better than stock imagery.

- Use web images only when identity or evidence matters; preserve the source
  URL in the project.
- Use AI imagery only when it materially improves a page. Prepare a compact
  `images/image_prompts.json` and call exactly one bounded command:

```bash
"${AXION_AGENT_BIN_PATH}" ppt-process images \
  --skill-dir "${SKILL_DIR}" --project-dir "${PPT_PROJECT_DIR}"
```

- The host always injects `AXION_AGENT_BIN_PATH`. Invoke it directly using the
  host system prompt's shell syntax; never test, print, search, infer, or retry
  interpolation variants.
- Follow its `next_action`. Do not invoke image providers or image scripts
  directly and do not explore fallback providers.
- Sync only icons actually needed by the roster; prefer one coherent family.

### Active-context page plan

Before writing P01, settle a compact page roster in context: one sentence per
page containing the page role, takeaway, evidence, and primary visual carrier.
For every page choose the carrier independently from text, native shapes,
diagram, table, chart, or a prepared image. For every image page, carry the
image layout entry together with its page job: the relationship it must express,
direction source, parent contour, slot/rhythm system, image/shape action, and
any continuity role. Avoid ten pages of repeated cards.

Use a restrained system suitable for the audience:

- one concrete PowerPoint-safe font family;
- one dark text color, one surface/background system, one accent, and at most
  one semantic success/warning color pair;
- title, body, annotation, and numeric-display sizes that remain stable across
  the deck;
- one deck-level shape language covering contour family, corner character,
  stroke/fill behavior, depth, connector/arrow character, and recurrence. Keep
  it active across page-fit geometry independently of any optional motif; omit
  a motif only when it has no continuity job or would add false meaning, compete
  with the page message, or reduce clarity;
- repeated navigation/chrome may be consistent, but page geometry must follow
  each page's actual relationship and content density.

For a 16:9 business deck, start from `viewBox="0 0 1280 720"`, page margins of
about 56–72 units, titles around 30–38 pt, body around 17–22 pt, and annotations
around 12–15 pt. These are starting anchors, not permission to shrink text to
hide overflow.

## 3. Direct SVG authoring

Write the complete SVG roster to `<PPT_PROJECT_DIR>/svg_output/`. Use one
zero-padded filename width, such as `01_cover.svg` through `10_end.svg`, and set
one root `data-pptx-page-role` from `cover`, `toc`, `section`, `content`, or
`ending`. Every page must use the same canvas.

### Required SVG contract

- Use ordinary SVG elements (`rect`, `path`, `line`, `circle`, `image`, `text`,
  `tspan`, and groups). Do not use `foreignObject`, HTML, external CSS, remote
  runtime dependencies, or unsupported filters.
- Keep every visible object inside the viewBox. Reserve margins and a body frame
  before placing details; never cover the title, footer, or page number.
- Treat SVG text as explicitly laid out. Do not rely on browser word wrapping.
  Shorten prose first; otherwise write deliberate line-level `text`/`tspan`
  positions with stable line height. Never reduce a recurring body role below
  the selected readable size just to make text fit.
- Keep text editable: do not outline ordinary text and do not flatten a slide
  or a text panel into an image.
- Reference only project-local prepared image assets. Crop with an explicit
  clip path or `preserveAspectRatio`; never distort an image to fill a box.
- Use a shallow, meaningful group structure and unique IDs. Every direct-root
  `<g>` must have a stable unique `id`. Every element carrying any
  `data-pptx-role` must also have a stable unique `id`, including full-canvas
  backgrounds, decorative lines/frames, and decorative text. Do not defer these
  IDs to the checker or repair pass. Do not place invisible objects outside the
  canvas or retain unused template debris.
- Every visible direct-root `<g>` is a semantic module and must declare positive
  root-coordinate `data-pptx-bounds="x y width height"` enclosing all of its
  text plus normal wrapping headroom. Nested groups carry no bounds. Full-canvas
  background/decoration primitives may stay outside groups when they have a
  stable ID and `data-pptx-role="background"` or `"decoration"`.
- Prefer native vector shapes and direct connectors for process, hierarchy,
  comparison, timeline, and system relationships. Make direction and grouping
  visually explicit instead of explaining them in prose.
- Before assigning coordinates on each page, resolve its actual native geometry
  from the page-scale job, semantic relationships, and retained deck shape
  language. Reuse a geometry signature only for the same job/relationship or a
  deliberate continuity motif. Zero preset use alone neither proves fit nor
  establishes a defect; generic repeated boxes are not a neutral fallback. Any
  Visual Job Router consulted here is recall for plausible expressions, never a
  gate, checklist, or permission boundary.
- Use shadows, gradients, clipping, and transparency sparingly. Keep important
  text on solid or predictably high-contrast surfaces.

### Content-fit discipline

The PPTX is the delivery truth. SVG authoring must nevertheless prevent obvious
overflow before export:

1. Keep titles to one or two deliberate lines and body statements concise.
2. Give every text block a known width and maximum line count.
3. If content exceeds that box, first remove repetition, then restructure into
   labels plus evidence, then split the idea only when the requested page count
   permits it.
4. Do not patch the exported PPTX during authoring. The post-export `review`
   command owns bounded native text repair against the actual rendered PPTX.

### Charts and tables

Use a chart only for actual quantitative values and a table only for a real
row-by-column comparison. Keep source values in context and verify arithmetic
with a calculator or a short read-only computation.

Each chart SVG must contain one stable marker per independent chart, for example:

```svg
<desc>chart-plot-area: object=roi-scenarios | x=120,y=190,w=1040,h=390</desc>
```

The object key must be unique within the page and stable across a repair. Direct
chart marks must correspond to the stated values; percentage parts must use a
consistent denominator; axes must not imply a false scale. Do not add a chart
marker to decorative geometry.

### Pacing

Calibrate the visual identity on P01 and ordinary content geometry on the first
content page. Then issue up to four independent `fs_write` calls in the same
assistant turn for consecutive pages; do not spend one model round trip per
page. Do not reread a successfully written page unless a later checker names
it. After the full roster exists, go directly to delivery; do not run a
separate first-page or per-page checker loop.

## 4. Delivery and actual-PPTX review

Run the fork-owned serial delivery command with exactly one notes mode:

```bash
"${AXION_AGENT_BIN_PATH}" ppt-process deliver \
  --skill-dir "${SKILL_DIR}" \
  --project-dir "${PPT_PROJECT_DIR}" \
  --quick-generate --no-notes
```

Use `--with-notes` only after the explicitly requested notes workflow has
created and split the notes. Do not call `finalize_svg.py`,
`svg_quality_checker.py`, `svg_to_pptx.py`, LibreOffice, or a rasterizer
directly. `deliver` owns the final SVG checker, conditional semantic gates,
export, package inspection, LibreOffice render, page PNGs, contact sheet, and
stable shape index.

Treat the returned JSON as the recovery authority:

- `failure_class=authoring-input`, `stage=svg-check`: read only the named bounded
  diagnostics, repair the owning SVG/resource once, and rerun `deliver`.
- `failure_class=authoring-input`, `stage=conditional-gates`: use only
  `required_receipts`. For `carrier`, compare its supplied carrier facts with
  the active page jobs, retained deck shape language, any adopted motif, and
  actual geometry signatures; counts are not quotas and zero preset use is
  evidence-neutral. Write the exact path/schema/fingerprint/hash with
  `status=passed`. For `chart`, recheck every supplied object against its source
  values, preserve each supplied `slide` and `object`, add the actual `mode`
  (for example `direct-calc`) and `status=passed`, then write the exact supplied
  path/schema/fingerprint and top-level `status=passed`. If a semantic check
  fails, repair the SVG first and rerun `deliver` to obtain a new fingerprint.
- `failure_class=mechanical`: stop. Report `next_action.instruction` and its
  `retry_command` to the operator. Do not change SVG, re-export, invoke an LLM,
  inspect scripts, or try another renderer.

`next_action.owner=operator` is a terminal handoff for the current agent turn.
The returned `retry_command` is an operator instruction, not authorization for
the agent to execute it, probe the environment, or add a transient retry.

After delivery passes, run exactly one actual-PPTX review:

```bash
"${AXION_AGENT_BIN_PATH}" ppt-process review \
  --skill-dir "${SKILL_DIR}" \
  --project-dir "${PPT_PROJECT_DIR}" \
  --pptx "<pptx returned by deliver>"
```

Only this command sends the rendered PPTX pages to a multimodal chat model. It
owns the at-most-two-round candidate → native text patch → render → affected
page recheck → publish loop, `validation/native-repairs.json`, backup, rollback,
and atomic replacement. Do not load its contact sheet into the parent agent,
modify SVG for a PPTX-only fit defect, or hand-edit OOXML.

`no-change` and `published` are success. For `rolled-back`, `reviewer`, or
`mechanical`, follow the returned `next_action` and retain the original PPTX.
Any failed `review` result is terminal for the current agent turn when
`next_action.owner=operator`: report its instruction and exact retry command;
do not probe Python, credentials, scripts, command discovery, or alternate
review paths.

## 5. Completion

Before reporting success, require all of the following:

- the requested page count and canvas are present;
- source-dependent claims and actual chart values remain traceable;
- the retained deck shape language is visible in page-fit geometry without
  forcing an optional motif or a native-preset quota;
- `deliver` passed its SVG, carrier, conditional chart, package, and render
  stages;
- `review` ended `no-change` or `published` against the actual PPTX render;
- exactly one final editable PPTX is identified, plus any explicitly requested
  notes/audio/video artifacts;
- no root design spec, lock, confirmation payload, delegated page author, or
  alternate rendering path was introduced.

Return the final absolute file path, the page count, the review outcome, and any
remaining operator action from structured `next_action` output.
