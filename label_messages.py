import json

# === Functions ===

def label_message(rubric, sacrifice=False):
    if rubric.get("appropriateness", 5) == 1:
        return 0, "blunder"  # Average is irrelevant if it's a blunder
    
    categories = [
        "understandability", "interestingness", "contextuality",
        "naturalness", "timeliness", "repetitiveness", "appropriateness"
    ]
    
    scores = []
    for cat in categories:
        score = rubric.get(cat, None)
        if score is not None:  # skip missing categories
            scores.append(score)
    
    avg = sum(scores) / len(scores) if scores else 0
    return avg, None  # Label determined later

def assign_label_from_score(avg):
    if avg >= 4.5:
        return "best"
    elif avg >= 4.3:
        return "excellent"
    elif avg >= 4:
        return "good"
    elif avg >= 3.5:
        return "inaccuracy"
    elif avg >= 3:
        return "mistake"
    else:
        return "blunder"

def process_conversations(data):
    simplified_data = []
    for convo in data:
        conv_id = convo.get("conversation_id", "unknown")
        messages = convo.get("messages", [])
        for i, msg in enumerate(messages):
            rubric = msg.get("rubric", {})
            speaker = msg.get("speaker", "unknown")
            sacrifice = msg.get("sacrifice", False)
            avg_score, base_label = label_message(rubric, sacrifice)
            msg["average_score"] = round(avg_score, 2)

            # Handle special cases
            if avg_score >= 4.5 and sacrifice:
                label = "brilliant"
            elif i > 0:
                prev_avg = messages[i - 1].get("average_score", 5)
                if prev_avg < 3:
                    if avg_score >= 4:
                        label = "great"
                    elif 3 <= avg_score < 4:
                        label = "miss"
                    else:  # avg_score < 3
                        label = "blunder"
                else:
                    label = assign_label_from_score(avg_score)
            else:
                label = assign_label_from_score(avg_score)

            simplified_data.append({
                "conversation_id": conv_id,
                "speaker": speaker,
                "text": msg.get("text", ""),
                "label": label
            })
    return simplified_data

# === Main Script ===

INPUT_FILE = "data/Message_data.json"
OUTPUT_FILE = "data/messages_labeled.json"

# Load JSON data
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# Process and assign labels
simplifed_messages = process_conversations(data)

# Save labeled data
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(simplifed_messages, f, indent=4, ensure_ascii=False)

print(f"✅ Labeled {sum(len(c.get('messages', [])) for c in data)} messages in {len(data)} conversations. Saved to {OUTPUT_FILE}")