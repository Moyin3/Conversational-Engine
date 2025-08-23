import json
from collections import defaultdict

# Load your flat per-message JSON
with open("data/messages_labeled.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Group messages by conversation_id
bundled_dict = defaultdict(list)
for msg in data:
    convo_id = msg.get("conversation_id", "unknown")
    bundled_dict[convo_id].append({
        "speaker": msg.get("speaker", ""),
        "text": msg.get("text", ""),
        "timestamp": msg.get("timestamp"),
        "label": msg.get("label", "")
    })

# Build final bundled structure
bundled = []
for convo_id, messages in bundled_dict.items():
    bundled.append({
        "conversation_id": convo_id,
        "messages": messages
    })

# Save bundled conversations
with open("data/conversations_bundled_with_labels.json", "w", encoding="utf-8") as f:
    json.dump(bundled, f, indent=2, ensure_ascii=False)

print(f"✅ Bundled {len(bundled)} conversations with labels")