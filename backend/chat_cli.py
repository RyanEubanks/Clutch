import json
import urllib.request

URL = "http://127.0.0.1:5001/api/chat"
messages = []

print("Tutor chat. Type 'quit' to exit.\n")
while True:
    text = input("You: ").strip()
    if text.lower() in ("quit", "exit"):
        break
    if not text:
        continue

    messages.append({"role": "user", "content": text})
    req = urllib.request.Request(
        URL,
        data=json.dumps({"messages": messages}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            reply = json.load(resp)["reply"]
    except Exception as exc:
        print(f"Error: {exc}\n")
        messages.pop()  # don't keep a message that got no reply
        continue

    messages.append({"role": "assistant", "content": reply})
    print(f"\nTutor: {reply}\n")