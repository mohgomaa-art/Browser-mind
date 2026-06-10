import google.genai as genai, os
c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
for model in ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash-exp"]:
    try:
        r = c.models.generate_content(model=model, contents="Say: ok")
        print(f"{model}: OK -> {r.text[:60]}")
        break
    except Exception as e:
        msg = str(e)[:150]
        print(f"{model}: {msg}")
