# AI Use Policy (public mirror of /page/ai-use)

LLMs (GLM initially, behind a provider abstraction) are used for: atomic claim
extraction, resolving multilingual ambiguity, and writing Persian copy FROM a
structured, pre-verified fact bundle. They are never used for hashing, routing,
formatting or DB logic. Every generated story passes an independent evidence audit:
each factual paragraph must reference verified claim IDs; unsupported paragraphs are
removed and unsupported stories are never published. External text is treated as
untrusted data (delimited blocks) and can never alter instructions or trigger
actions. Automation attribution is truthful (organization-level, no fake authors).
