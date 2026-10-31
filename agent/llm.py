import os
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv is in requirements.txt; env vars still work without it
    pass

FALLBACK = not os.getenv("GEMINI_API_KEY")
if FALLBACK:
    print("\n" + "!" * 70
          + "\n!! GEMINI_API_KEY not set: agent is running on CANNED RESPONSES, NOT the LLM"
          + "\n" + "!" * 70 + "\n")


MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def complete(system_prompt, messages):
    """The only provider call. messages: [{"role": "user"|"assistant", "content": str}], first is user."""
    from google import genai  # lazy: fallback mode must not need the package
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    contents = [types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part(text=m["content"])])
                for m in messages]
    # thinking off: it adds seconds per turn on a live call. 120 tokens: 40 Devanagari/Tamil words need more than 100
    cfg = types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.4, max_output_tokens=120,
                                      thinking_config=types.ThinkingConfig(thinking_budget=0))
    start = time.perf_counter()
    try:
        return client.models.generate_content(model=MODEL, contents=contents, config=cfg).text
    finally:
        print(f"[llm] {MODEL} call took {time.perf_counter() - start:.2f}s")
