"""Prompt templates for LLM-powered paper analysis."""

# --- Summary ---

SUMMARY_SYSTEM = (
    "You are an academic paper analyst. "
    "Output valid JSON only. No markdown, no code fences, no explanation."
)

SUMMARY_USER = """Analyze the following academic paper text and output a JSON object with exactly these fields:

{{
  "one_sentence_summary": "One sentence summarizing the paper's main contribution",
  "research_question": "What problem or question does this paper address?",
  "method": "What is the core methodology or approach?",
  "conclusions": "What are the main conclusions or findings?",
  "use_cases": "What are the practical applications or use cases?",
  "limitations": "What are the acknowledged or apparent limitations?",
  "relation_to_prior_work": "How does this work relate to or differ from prior research?"
}}

Paper text:
{paper_text}"""


# --- Q&A ---

QA_SYSTEM = (
    "You are an academic paper Q&A generator. "
    "Output valid JSON only. No markdown, no code fences, no explanation."
)

QA_USER = """Generate 5-8 question-answer pairs from the following academic paper.
Cover: motivation, method, experiments, results, limitations, and future work.

Output a JSON object with a "questions" array:
{{
  "questions": [
    {{"question": "...", "answer": "..."}},
    ...
  ]
}}

Paper text:
{paper_text}"""


# --- Glossary ---

GLOSSARY_SYSTEM = (
    "You are a technical terminology expert. "
    "Output valid JSON only. No markdown, no code fences, no explanation."
)

GLOSSARY_USER = """Extract 10-20 key technical terms from the following academic paper.
For each term, provide the English term, Chinese translation, definition, and the section where it first appears.

Output a JSON object with an "entries" array:
{{
  "entries": [
    {{"term_en": "...", "term_zh": "...", "definition": "...", "section": "..."}},
    ...
  ]
}}

Paper text:
{paper_text}"""


# --- Translation ---

TRANSLATE_SYSTEM = (
    "You are an academic translator (English to Chinese). "
    "Preserve markdown format. "
    "Keep technical terms in English with Chinese explanation in parentheses. "
    "Output only the translated text, no extra commentary."
)

TRANSLATE_USER = """Translate the following academic paper text from English to Chinese.
Preserve all markdown formatting (headers, lists, bold, italic, code blocks).
Keep technical terms in English with Chinese in parentheses, e.g. Transformer(变换器).

Text to translate:
{text}"""
