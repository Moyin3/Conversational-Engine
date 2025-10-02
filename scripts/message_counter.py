FILE_PATH = "data/Message_data3.json"  # Adjust if needed
LINE_LIMIT = 23502  # Change to the line number where your error begins

def count_messages(file_path, line_limit):
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            if i >= line_limit:
                break
            if '"speaker":' in line:
                count += 1
    return count

if __name__ == "__main__":
    total = count_messages(FILE_PATH, LINE_LIMIT)
    print(f"✅ Total messages before line {LINE_LIMIT}: {total}")