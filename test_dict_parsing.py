#!/usr/bin/env python3

import json
import re

# Simulate the problematic LLM response from logs
llm_response = '''{ "source": "playing", "target": "игра", "category": "" },\n { "source": "transition", "target": "переход", "category": "" },\n { "source": "eight", "target": "восемь", "category": "" }\n ]\n}\n'''

print("Testing current _save_vocabulary_formatted logic...")

# Current logic from app.py
translations = {}
try:
    vocab_json = json.loads(llm_response)
    terms = vocab_json.get('terms', [])
    print(f"JSON parsed successfully: {len(terms)} terms")
except (json.JSONDecodeError, AttributeError) as e:
    print(f"JSON parsing failed: {e}")
    # This is what happens in reality!
    for line in llm_response.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            parts = line.split('=', 1)
            source = parts[0].strip()
            target = parts[1].strip()
            translations[source.lower()] = (source, target)

print(f"Final translations count: {len(translations)}")

# The problem: JSON is malformed because it has extra text/formatting
# Let's try to extract JSON properly
print("\nTrying to extract JSON with regex...")
json_match = re.search(r'\{.*"terms".*\[.*\].*\}', llm_response, re.DOTALL)
if json_match:
    print("Found JSON-like structure!")
    try:
        data = json.loads(json_match.group(0))
        print(f"Successfully parsed extracted JSON: {len(data.get('terms', []))} terms")
    except json.JSONDecodeError as e:
        print(f"Still failed: {e}")
else:
    print("No JSON structure found")

# Try array extraction
array_match = re.search(r'\[.*\]', llm_response, re.DOTALL)
if array_match:
    print("Found array structure!")
    try:
        terms = json.loads(array_match.group(0))
        print(f"Successfully parsed array: {len(terms)} terms")
    except json.JSONDecodeError as e:
        print(f"Array parsing failed: {e}")