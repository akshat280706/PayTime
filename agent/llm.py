import os

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


def complete(system_prompt, messages):
    """The only provider call. messages: [{"role": "user"|"assistant", "content": str}], first is user."""
    import google.generativeai as genai  # lazy: fallback mode must not need the package

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                                  system_instruction=system_prompt)
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [m["content"]]}
                for m in messages]
    cfg = {"temperature": 0.4, "max_output_tokens": 300}
    return model.generate_content(contents, generation_config=cfg).text
