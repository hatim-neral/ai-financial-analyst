"""Central limits and display settings. Everything security-relevant lives here so it
is easy to review in one place."""

# --- Upload limits -------------------------------------------------------------
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB; also enforced by .streamlit/config.toml
MAX_ROWS = 50_000
# If more than this share of data rows fail validation, reject the whole file:
# it almost certainly is not in the expected format.
MAX_INVALID_SHARE = 0.5
MAX_CATEGORY_CHARS = 60
MAX_DESCRIPTION_CHARS = 200
MAX_ABS_AMOUNT = 1e13

# --- Q&A limits ----------------------------------------------------------------
MAX_QUESTION_CHARS = 500
MAX_QUESTIONS_PER_SESSION = 30
MAX_AGENT_STEPS = 6          # LLM round trips per question (tool calls + answer)
MAX_TOOL_CALLS_PER_STEP = 6
MAX_GUARD_RETRIES = 1        # re-ask the LLM once if it states an unverified figure
HISTORY_TURNS = 3            # previous Q&A pairs passed back for follow-up questions
LLM_TIMEOUT_S = 30
LLM_MAX_OUTPUT_TOKENS = 1500     # reasoning models spend part of this thinking
LLM_MAX_RATE_LIMIT_WAIT_S = 45   # wait out a short "try again in Ns" instead of failing
LLM_RATE_LIMIT_RETRIES = 3

# --- Display -------------------------------------------------------------------
CURRENCY = "₹"
