# kanto-heat-analysis

Investigation of the mechanistic drivers of Kanto surface heat extremes, tracing the causal chain from Kanto land-surface variables through Baiu monsoon termination timing, North Pacific subtropical high circulation, and terminating at Western Pacific / Indian Ocean SST forcing.

This repository hosts both the SA2 poster deliverable and the broader mechanistic investigation as a single unified codebase. The Capstone boundary is administrative, not intellectual.

---

## Research Questions

- **RQ1:** Has heat wave frequency/intensity over Kanto trended upward across the study period?
- **RQ2:** Has Baiu termination date shifted earlier, and does that trend align with the RQ1 signal?
- **RQ3:** Does earlier Baiu termination predict greater heat wave severity in the following summer (Baiu–heat coupling)?

---

## Data Access

ERA5 and ERA5-Land data are **not committed** to this repository (Copernicus licensing; file sizes).

See [`data/README.md`](data/README.md) for complete CDS API download instructions and a ready-to-run download script.

---

## Reproduction

1. Clone the repo.
2. Create the conda environment: `conda env create -f environment.yml`
3. Activate it: `conda activate kanto-heat`
4. Download data per `data/README.md`.
5. Run notebooks in order: `01_data_prep` → `07_sst_forcing`.

---

## Structure

```
kanto-heat-analysis/
├── notebooks/          # Unified analysis ordered by causal chain
├── figures/            # All outputs, tagged by source notebook
├── capstone/           # Administrative Capstone layer (poster, submission, map)
├── data/               # No data files — CDS API instructions only
├── src/                # Shared utility functions
├── references.bib      # BibTeX bibliography
└── environment.yml     # Pinned conda environment
```

See [`capstone/CAPSTONE_MAP.md`](capstone/CAPSTONE_MAP.md) for a panel-by-panel mapping of the SA2 poster to notebooks and figures.

---

## AI Usage

### University of Leeds Policy (OLDA5302M)

Generative AI is classified **Amber** for this module: permitted in an assistive role for specifically designed processes. Permitted uses include research design brainstorming, learning support, code development assistance (library suggestions, syntax, debugging), visualisation suggestions, and documentation support (proofreading, clarity, structure, word count reduction).

AI must not be used to produce the entirety of, or sections of, submitted assessment work.

Per university requirements:
- AI usage is acknowledged in the SA2 submission with: tool name and version, publisher, URL, and a one-sentence description of context
- AI usage is mentioned in the SA2 audio narration
- Prompt and response logs are maintained to demonstrate academic integrity

**Tool used:** Claude Code (Anthropic, `claude-sonnet-4-6`) · https://claude.ai/code

For the University of Leeds' full guidance on generative AI assessment categories, see: https://generative-ai.leeds.ac.uk/ai-and-assessments/categories-of-assessments/

---

### Personal Charter

The Amber policy defines the floor. The following rules define the author's own standard, which is stricter in the analytical domain.

**Rule 1 — Code: Infrastructure is Claude's, Analysis is the Author's**

Claude Code writes and maintains infrastructure and repository operations: git commits, pull requests, repo setup, data download orchestration, utility scaffolding, and documentation. Claude Code does not write analytical code — statistical models, data transformations, index computations, or visualisations that directly embody the research. Every line of analysis code is written by the author and understood well enough to be explained and defended in the SA2 narration. For the analytical work, Claude Code acts as a technical advisor: explaining concepts, debugging code the author has written, and suggesting approaches for the author to evaluate and implement.

**Rule 2 — Literature: Primary Sources First**

Claude Code may suggest relevant papers and discuss material the author has already read. It must not summarise papers as a substitute for reading them. Understanding a source through an AI summary is not the same as understanding it, and in a domain as specific as East Asian monsoon dynamics, the nuance matters.

**Rule 3 — Ideas Must Be the Author's**

Claude Code may help sharpen, restructure, or articulate arguments and writing the author has drafted. It must not generate research framing, analytical conclusions, or poster narrative wholesale. All research questions, modelling decisions, interpretations of results, and conclusions are the author's own.
