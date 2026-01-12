from collections import Counter
import spacy
import torch
import numpy as np
import cupy as cp
from icecream import ic
from src.config import Config

# Initialize config
config = Config()

def make_vocab(text, stop_words=None):
    if config.debug:
        ic("Starting Named Entity Recognition")
    if not text:
        if config.debug:
            ic("No text to process.")
        return

    # Define default stop words or use user provided
    default_stop_words = set([
        "the", "and", "p", "emphasis", "section", "first", "second", "one", "two"
    ])

    if stop_words is None:
        stop_words = default_stop_words
    else:
        stop_words = set(stop_words)

    try:
        # Ensure PyTorch is using CUDA
        if not torch.cuda.is_available():
            if config.debug:
                ic("CUDA is not available. Falling back to CPU.")
        else:
            if config.debug:
                ic("CUDA is available. Using GPU.")

        # Prefer GPU usage in spaCy
        gpu = spacy.prefer_gpu()
        if config.debug:
            ic(gpu)
        nlp = spacy.load(config.nermodel)
        nlp.max_length = 110000

        # Split text into chunks of up to 100,000 characters
        chunk_size = 100000
        text_chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        ner_category = ["ORG", "LOC", "GPE", "PERSON"]
        ents = []
        for chunk in text_chunks:
            doc = nlp(chunk)
            ents.extend([
                (ent.text.strip(), ent.label_, tuple(ent.vector.get()) if hasattr(ent.vector, 'get') else tuple(ent.vector) if ent.vector.size > 0 else None)
                for ent in doc.ents if ent.vector_norm != 0 and ent.label_ in ner_category
            ])

            if config.debug:
                ic(f"Found entities: {len(ents)}")

    except Exception as e:
        if config.debug:
            ic(f"Error loading spaCy model: {e}")
        return

    # Count occurrences of each entity
    item_counts = Counter((text, label) for text, label, vector in ents)
    unique_ents = [(text, label, next((vector for t2, l2, vector in ents if t2 == text and l2 == label), None), count)
                   for (text, label), count in item_counts.items()]

    if config.debug:
        ic(f"Unique entities before filtering by count: {len(unique_ents)}")

    # Filter out entities with less than 5 occurrences
    unique_ents = [ent for ent in unique_ents if ent[3] >= 5]

    if config.debug:
        ic(f"Unique entities after filtering by count: {len(unique_ents)}")

    # Merge entities that contain substrings of other entities
    merged_ents = []
    for ent1 in unique_ents:
        is_substring = False
        for ent2 in unique_ents:
            if ent1[0].lower() != ent2[0].lower() and ent1[0].lower() in ent2[0].lower():
                is_substring = True
                break
        if not is_substring:
            merged_ents.append(ent1)

    # Further merging to ensure the longest entity is kept
    final_merged_ents = []
    for ent1 in merged_ents:
        longer_ent_found = False
        for ent2 in merged_ents:
            if ent1[0].lower() != ent2[0].lower() and ent2[0].lower() in ent1[0].lower():
                longer_ent_found = True
                break
        if not longer_ent_found:
            final_merged_ents.append(ent1)

    if config.debug:
        ic(f"Unique entities after merging: {len(final_merged_ents)}")

    # Find most common words with count > 10 and length > 5
    word_counts = Counter(
        token.text for token in doc if token.is_alpha and token.text not in stop_words)

    # Filter words with count > 4 and length > 5
    filtered_words_with_counts = [(word, count) for word, count in word_counts.items() if count > 10 and len(word) > 5]

    sorted_common_words_with_counts = sorted(filtered_words_with_counts, key=lambda x: x[1], reverse=True)
    top_common_words = [word for word, count in sorted_common_words_with_counts]

    if config.debug:
        ic(f"Top common words with counts: {sorted_common_words_with_counts}")

    # Normalize final_merged_ents
    seen_entities = set()
    normalized_final_merged_ents = []
    for ent in final_merged_ents:
        normalized_text = ent[0].strip().lower()
        if normalized_text not in seen_entities and normalized_text not in stop_words:
            seen_entities.add(normalized_text)
            normalized_final_merged_ents.append((ent[0], ent[1]))

    # Normalize top_common_words
    seen_words = set()
    normalized_top_common_words = []
    for word in top_common_words:
        normalized_word = word.strip().lower()
        if normalized_word not in seen_entities and normalized_word not in stop_words:
            seen_words.add(normalized_word)
            normalized_top_common_words.append(word)

    # Remove words from top_common_words that are substrings of entities
    for ent in final_merged_ents:
        words_in_ent = ent[0].strip().lower().split()
        for word in words_in_ent:
            if word in seen_words and word not in stop_words:
                seen_words.remove(word)

    unique_top_common_words = [word for word in normalized_top_common_words if word.lower() in seen_words]

    result_list = [f"{text} ({label})" for text, label in normalized_final_merged_ents] + unique_top_common_words

    if config.debug:
        ic("Finished processing.")
    return '\n'.join(result_list) + '\n'


def find_matching_words_with_cosine_similarity(text, vocab, lng, threshold=0.8, batch_size=1024):
    if config.debug:
        ic("Starting cosine similarity matching")

    if not text or not vocab:
        if config.debug:
            ic("No text or vocabulary to process.")
        return []

    try:
        spacy.prefer_gpu()
        nlp = spacy.load(config.nermodel)
        nlp.max_length = 110000
        doc = nlp(text)
    except Exception as e:
        if config.debug:
            ic(f"Error loading spaCy model: {e}")
        return []

    orig_values = [entry[lng] for entry in vocab.values() if lng in entry]
    
    valid_vocab_words = []
    vocab_vectors = []

    for phrase in orig_values:
        sub_words = phrase.split()
        sub_docs = list(nlp.pipe(sub_words, disable=["ner", "parser", "tagger"]))
        sub_vecs = [d.vector for d in sub_docs if d.vector_norm != 0]

        if sub_vecs:
            mean_vec = np.mean(np.vstack(sub_vecs), axis=0)
            vocab_vectors.append(mean_vec)
            valid_vocab_words.append(phrase)

    if not vocab_vectors:
        if config.debug:
            ic("No valid vectors in vocab.")
        return []

    # numpy -> cupy
    vocab_matrix = cp.asarray(np.vstack(vocab_vectors))
    vocab_matrix = vocab_matrix / cp.linalg.norm(vocab_matrix, axis=1, keepdims=True)

    matched_words_set = set()

    tokens = [t for t in doc if t.is_alpha and t.vector_norm != 0]
    for i in range(0, len(tokens), batch_size):
        batch_tokens = tokens[i:i+batch_size]
        token_vectors = np.vstack([t.vector for t in batch_tokens])
        token_vectors = cp.asarray(token_vectors)
        token_vectors = token_vectors / cp.linalg.norm(token_vectors, axis=1, keepdims=True)

        sims = cp.dot(token_vectors, vocab_matrix.T)

        best_matches = cp.where(sims > threshold)
        for _, vi in zip(*best_matches):
            matched_words_set.add(valid_vocab_words[int(vi)])

    if config.debug:
        ic(f"Found matching words: {matched_words_set}")
    return list(matched_words_set)
