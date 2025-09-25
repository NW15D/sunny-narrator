from sklearn.metrics.pairwise import cosine_similarity
from icecream import ic
import app
from collections import Counter
import torch
import multiprocessing as mp
mp.set_start_method('spawn', force=True)
from joblib import Parallel, delayed
from itertools import cycle
import cupy
import spacy
import torch

from thinc.api import set_gpu_allocator, require_gpu

#########
import cupy
from joblib import Parallel, delayed

def chunker(iterable, total_length, chunksize):
    return (iterable[pos: pos + chunksize] for pos in range(0, total_length, chunksize))

#def flatten(list_of_lists):
#    "Flatten a list of lists to a combined list"
#    return [item for sublist in list_of_lists for item in sublist]

def process_entity(doc):
    """Возвращает список найденных сущностей (NER)"""
    ner_category = ["PERSON", "ORG", "LOC"]
    ents = []
    for ent in doc.ents:
        if ent.vector_norm != 0 and ent.label_ in ner_category:
            # Strip whitespace and newline characters from the entity text
            clean_text = ent.text.strip()
            # Convert vector to a tuple if it exists, otherwise use None
            vector = tuple(ent.vector.get()) if hasattr(ent.vector, 'get') else tuple(
                ent.vector) if ent.vector.size > 0 else None
            ents.append((clean_text, ent.label_, vector))

    return ents

def process_chunk(texts, rank):
    print(f"Обрабатывается на GPU {rank}")
    with cupy.cuda.Device(rank):
        set_gpu_allocator("pytorch")
        require_gpu(rank)
        nlp = spacy.load("en_core_web_trf")
        preproc_pipe = []
        for doc in nlp.pipe(texts, batch_size=20):
            preproc_pipe.extend(process_entity(doc))  # добавляем сущности в общий список
        return preproc_pipe

def preprocess_parallel(texts, chunksize=100000):
    executor = Parallel(n_jobs=2, backend='multiprocessing', prefer="processes")
    do = delayed(process_chunk)
    tasks = []
    gpus = list(range(0, cupy.cuda.runtime.getDeviceCount()))
    rank = 0
    for chunk in chunker(texts, len(texts), chunksize=chunksize):
        tasks.append(do(chunk, rank))
        rank = (rank + 1) % len(gpus)
    result = executor(tasks)
    return result

#####################
#example
#texts = ["His friend Nicolas J. Smith is here with Bart Simpon and Fred."] * 5
#print(preprocess_parallel(texts=texts, chunksize=100000))
#################################

def make_vocab(text, stop_words=None):
    ic("Starting Named Entity Recognition")
    if not text:
        ic("No text to process.")
        return
    ic(torch.cuda.is_available())
    lst=preprocess_parallel(texts=text, chunksize=100000)
    ic(lst)
    # Определите список стопслов по умолчанию или используйте переданный пользователем
    default_stop_words = set([
        "the", "and", "p", "emphasis", "section","first", "second", "one","two"
        # Добавьте сюда остальные стопслова по необходимости
    ])

    if stop_words is None:
        stop_words = default_stop_words
    else:
        stop_words = set(stop_words)

    try:
        # Ensure PyTorch is using CUDA
        if not torch.cuda.is_available():
            ic("CUDA is not available. Falling back to CPU.")
        else:
            ic("CUDA is available. Using GPU.")

        # Prefer GPU usage in spaCy
        spacy.require_gpu()

        nlp = spacy.load(app.nermodel)
        nlp.max_length = 3500000
        doc = nlp("This is a test sentence.")
        ic(doc.ents)

        doc = nlp(text)
    except Exception as e:
        ic(f"Error loading spaCy model: {e}")
        return


    ner_category = ["PERSON", "ORG", "LOC"]
    ents = []
    for ent in doc.ents:
        if ent.vector_norm != 0 and ent.label_ in ner_category:
            # Strip whitespace and newline characters from the entity text
            clean_text = ent.text.strip()
            # Convert vector to a tuple if it exists, otherwise use None
            vector = tuple(ent.vector.get()) if hasattr(ent.vector, 'get') else tuple(
                ent.vector) if ent.vector.size > 0 else None
            ents.append((clean_text, ent.label_, vector))

    ic(f"Found entities: {len(ents)}")

    # Count occurrences of each entity
    item_counts = Counter((text, label) for text, label, vector in ents)
    unique_ents = [(text, label, next((vector for t2, l2, vector in ents if t2 == text and l2 == label), None), count)
                   for (text, label), count in item_counts.items()]

    ic(f"Unique entities before filtering by count: {len(unique_ents)}")

    # Filter out entities with less than 5 occurrences
    unique_ents = [ent for ent in unique_ents if ent[3] >= 5]

    ic(f"Unique entities after filtering by count: {len(unique_ents)}")

    # Merge entities that contain substrings of other entities, keeping only the longest one
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

    ic(f"Unique entities after merging: {len(final_merged_ents)}")

    # Find most common words with count > 50 and length > 5
    word_counts = Counter(
        token.text for token in doc if token.is_alpha and token.text not in stop_words)

    # Filter words with count > 20 and length > 5
    filtered_words_with_counts = [(word, count) for word, count in word_counts.items() if count > 10 and len(word) > 5]

    # Sort words by count in descending order and select
    sorted_common_words_with_counts = sorted(filtered_words_with_counts, key=lambda x: x[1], reverse=True)

    # Extract only the word part for further processing
    top_common_words = [word for word, count in sorted_common_words_with_counts]

    # Debugging output for common words with their counts
    ic(f"Top common words with counts: {sorted_common_words_with_counts}")

    # Normalize final_merged_ents by converting text to lowercase and stripping whitespace
    seen_entities = set()
    normalized_final_merged_ents = []
    for ent in final_merged_ents:
        normalized_text = ent[0].strip().lower()
        if normalized_text not in seen_entities and normalized_text not in stop_words:
            seen_entities.add(normalized_text)
            # Append the entity with its label in parentheses, keeping original case
            normalized_final_merged_ents.append((ent[0], ent[1]))

    # Normalize top_common_words by converting to lowercase for checking substrings
    seen_words = set()
    normalized_top_common_words = []
    for word in top_common_words:
        normalized_word = word.strip().lower()
        if normalized_word not in seen_entities and normalized_word not in stop_words:
            seen_words.add(normalized_word)
            # Append the original word for further processing
            normalized_top_common_words.append(word)

    # Remove words from top_common_words that are substrings of entities in final_merged_ents
    for ent in final_merged_ents:
        words_in_ent = ent[0].strip().lower().split()  # Предполагается, что слова разделены пробелами
        for word in words_in_ent:
            if word in seen_words and word not in stop_words:
                seen_words.remove(word)

    # Convert the set back to a list for top_common_words
    unique_top_common_words = [word for word in normalized_top_common_words if word.lower() in seen_words]

    # Combine lists and remove duplicates while preserving original case
    result_list = [f"{text} ({label})" for text, label in normalized_final_merged_ents] + unique_top_common_words

    ic("Finished processing.")
    return '\n'.join(result_list) + '\n'



def find_matching_words_with_cosine_similarity(text, vocab, lng):
    ic("Starting cosine similarity matching")


    if not text or not vocab:
        ic("No text or vocabulary to process.")
        return []

    try:
        spacy.require_gpu()
        #spacy.prefer_gpu()
        nlp = spacy.load(app.nermodel)
        nlp.max_length = 40000000
        doc = nlp(text)
    except Exception as e:
        ic(f"Error loading spaCy model: {e}")
        return []

    orig_values = [entry[lng] for entry in vocab.values() if lng in entry]
    #ic(orig_values)

    # Extract vectors from the vocab dictionary
    vocab_vectors = {}
    for word in orig_values:
        doc_en = nlp(word)
        try:
            if doc_en.vector_norm != 0:
                vocab_vectors[word] = doc_en.vector.get()
        except Exception as e:
            ic(f"Error processing word '{word}': {e}")

    # Find matches using cosine similarity
    matched_words_set = set()
    for token in doc:
        ic(token)
        if token.is_alpha and token.vector_norm != 0:
            token_vector = token.vector.get().reshape(1, -1)  # Convert to NumPy array
            for vocab_word, vocab_vector in vocab_vectors.items():
                # Split vocab_word into individual words if it contains spaces
                ic(vocab_word)
                sub_words = vocab_word.split()
                match_found = False
                for sub_word in sub_words:
                    ic(sub_word)
                    doc_sub_word = nlp(sub_word)
                    if doc_sub_word.vector_norm != 0:
                        sub_word_vector = doc_sub_word.vector.get().reshape(1, -1)
                        similarity = cosine_similarity(token_vector, sub_word_vector)[0][0]
                        if similarity > 0.8:
                            match_found = True
                            break
                if match_found:
                    matched_words_set.add(vocab_word)

    ic(f"Found matching words: {matched_words_set}")
    return list(matched_words_set)  # Return unique matched words
