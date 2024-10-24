# Import libraries
import pandas as pd
import json
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import nltk
from tqdm import tqdm
import csv
import numpy as np
from nltk.corpus import stopwords
import string 
import numpy as np
from scipy.sparse import lil_matrix, csr_matrix, save_npz, load_npz
from collections import defaultdict
import math
import pickle
import os

TOK_CORPUS_PATH = '../data/tokenized_corpus.pkl'
BM25_MATRIX_PATH = '../data/bm25_matrix.pkl'
IDX_TO_DOCID_PATH = '../data/idx_to_docid.pkl'

nltk.download('punkt')
nltk.download('stopwords')
nltk.download('punkt_tab')


def save_data(data, file_name):
    with open(file_name, 'wb') as f:
        pickle.dump(data, f)

def load_data(file_name):
    with open(file_name, 'rb') as f:
        return pickle.load(f)


# load corpus
with open('../data/corpus.json', 'r', encoding='utf-8') as f:
    corpus = json.load(f)

# from txt load korean stopwords 
with open('../data/stopwords-ko.txt', 'r', encoding='utf-8') as f:
    stopwords_ko = f.read().splitlines()

# load test data
test_data = pd.read_csv('../data/test.csv')

# prepare test queries in a similar format as the corpus
test_queries = [
    {'docid': row['id'], 'text': row['query'], 'lang': row['lang']}
    for idx, row in test_data.iterrows()
]

language_stopwords = {
    "en": set(stopwords.words('english')),
    "fr": set(stopwords.words('french')),
    "de": set(stopwords.words('german')),
    "ar": set(stopwords.words('arabic')),
    "es": set(stopwords.words('spanish')),
    "it": set(stopwords.words('italian')), 
    "ko": set(stopwords_ko),
} 

docid_to_text = {}
for doc in corpus:
    docid_to_text[doc['docid']] = doc['text']

# idx to docid per language
idx_to_docid = {
    "en": {},
    "fr": {},
    "de": {},
    "ar": {},
    "es": {},
    "it": {},
    "ko": {}
}

def tokenize_korean_simple(text):
    tokens = text.split()
    return tokens

def split_into_chunks(docid, text, chunk_size=500):
    """Split the document into chunks of specified size (in tokens) and return a list of chunks."""
    tokens = word_tokenize(text)
    return [(docid, tokens[i:i + chunk_size]) for i in range(0, len(tokens), chunk_size)]

def tokenize_with_chunks(docs, chunk_size=500):
    """Tokenize documents and split into chunks while preserving original document IDs and restarting chunk indices for each language."""
    tokenized_chunks = defaultdict(dict)  # Dictionary for tokenized chunks
    chunk_to_original_doc = defaultdict(dict)  # Mapping of chunk index to original doc ID, per language
    
    # Loop through all documents
    for doc in tqdm(docs, desc="Tokenizing and splitting into chunks"):
        docid = doc['docid']
        text = doc['text']
        lang = doc['lang']
        
        # Ensure we start a new chunk counter for each language
        if lang not in chunk_to_original_doc:
            chunk_counter = 0
        else:
            chunk_counter = max(chunk_to_original_doc[lang].keys(), default=-1) + 1
        
        text_no_punctuation = "".join([ch for ch in text if ch not in string.punctuation])

        # Split text into chunks
        chunks = split_into_chunks(docid, text_no_punctuation, chunk_size)

        # Tokenize each chunk
        for chunk_id, chunk in enumerate(chunks):
            chunk_docid, chunk_tokens = chunk
            if lang == 'ko':
                tokens = tokenize_korean_simple(" ".join(chunk_tokens))
            else:
                tokens = word_tokenize(" ".join(chunk_tokens))

            stop_words = language_stopwords.get(lang, set())
            filtered_tokens = [word.lower() for word in tokens if word.lower() not in stop_words]

            tf = defaultdict(int)
            for token in filtered_tokens:
                tf[token] += 1

            # Use the language-specific chunk_counter as the key and map it to the original document ID
            chunk_to_original_doc[lang][chunk_counter] = docid  # Map chunk to original doc
            tokenized_chunks[lang][chunk_counter] = {
                'tf': tf,
                'doc_len': len(filtered_tokens),
                'lang': lang
            }

            chunk_counter += 1 

    return tokenized_chunks, chunk_to_original_doc

def tokenize(docs):
    tokenized_docs = defaultdict(dict)

    for doc in tqdm(docs, desc="Tokenizing batch"):
        docid = doc['docid']
        text = doc['text']
        lang = doc['lang']

        text_no_punctuation = "".join([ch for ch in text if ch not in string.punctuation])
        
        if lang == 'ko':
            tokens = tokenize_korean_simple(text_no_punctuation)
        else:
            tokens = word_tokenize(text_no_punctuation)
        
        stop_words = language_stopwords.get(lang, set())
        filtered_tokens = [word.lower() for word in tokens if word.lower() not in stop_words]

        tf = defaultdict(int)
        for token in filtered_tokens:
            tf[token] += 1

        tokenized_docs[lang][docid] = {
            'tf': tf,
            'doc_len': len(filtered_tokens),
            'lang': lang
        }

    return tokenized_docs

def compute_corpus_statistics(tokenized_corpus_by_lang):
    idf_by_lang = {}
    avgdl_by_lang = {}

    for lang, tokenized_docs in tokenized_corpus_by_lang.items():
        df = defaultdict(int)
        total_doc_len = 0
        doc_count = len(tokenized_docs)

        for doc in tokenized_docs.values():
            tokens = doc['tf']  # Error occurs here
            total_doc_len += len(tokens)
            unique_tokens = set(tokens)
            for token in unique_tokens:
                df[token] += 1

        avgdl = total_doc_len / doc_count
        avgdl_by_lang[lang] = avgdl

        idf = {}
        for term, freq in df.items():
            idf[term] = math.log((doc_count - freq + 0.5) / (freq + 0.5) + 1)

        idf_by_lang[lang] = idf

    return idf_by_lang, avgdl_by_lang

def build_sparse_matrix(docs_or_queries, vocab, idfs, avgdl, lang, is_query=False, k1=1.2, b=0.7):
    """Builds a sparse matrix from documents or queries."""
    matrix = lil_matrix((len(docs_or_queries), len(vocab)), dtype=np.float32)

    if not is_query:
        for doc_id, doc in enumerate(docs_or_queries):
            doc_len = docs_or_queries[doc]['doc_len']
            norm_factor = k1 * (1 - b + b * doc_len / avgdl)
            idx_to_docid[lang][doc_id] = doc
            for term, freq in docs_or_queries[doc]['tf'].items():
                term_index = vocab[term]
                tf_adjusted = freq * (k1 + 1) / (freq + norm_factor)
                matrix[doc_id, term_index] = tf_adjusted * idfs.get(term, 0)         
    else:
        for query_id, query in enumerate(docs_or_queries):
            for term, freq in docs_or_queries[query]['tf'].items():
                if term in vocab:
                    term_index = vocab[term]
                    matrix[query_id, term_index] = freq  # Simply the term frequency in query

    return csr_matrix(matrix)

# save results to csv
def write_submission_csv(results_final, output_path):
    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['id', 'docids'])
        for idx, docs in results_final.items():
            # save as list like this: 0,"['doc-en-0', 'doc-de-14895', 'doc-en-829265', 'doc-en-147113', 'doc-en-644359', 'doc-en-585315', 'doc-en-234047', 'doc-en-14117', 'doc-en-794977', 'doc-en-374766']"
            writer.writerow([idx, str(docs)])

print("Tokenizing corpus with chunks...")
if os.path.exists(TOK_CORPUS_PATH):
    tokenized_corpus_by_lang, chunk_to_original_doc = load_data(TOK_CORPUS_PATH)
    # print(chunk_to_original_doc)
else:
    tokenized_corpus_by_lang, chunk_to_original_doc = tokenize_with_chunks(corpus)
    save_data((tokenized_corpus_by_lang, chunk_to_original_doc), TOK_CORPUS_PATH)

print("Tokenizing queries...")
tokenized_queries_by_lang = tokenize(test_queries)

print("Building vocab...")
# make vocab per language
vocab_by_lang = {}
for lang, tokenized_docs in tokenized_corpus_by_lang.items():
    vocab = set()
    for doc in tokenized_docs.values():
        vocab.update(doc['tf'].keys())
    vocab_by_lang[lang] = vocab

print("Retrieving results...")
# now call build sparse matrix per language
results_final = {}
bm25_matrix = {}
scores_matrix_lang = {}

if os.path.exists(BM25_MATRIX_PATH):
    bm25_matrix = load_data(BM25_MATRIX_PATH)

idf_by_lang, avgdl_by_lang = compute_corpus_statistics(tokenized_corpus_by_lang)
for lang in tqdm(tokenized_queries_by_lang, desc="Retrieving results"):
    vocab = {term: idx for idx, term in enumerate(vocab_by_lang[lang])}

    if lang not in tokenized_corpus_by_lang:
        continue 

    if bm25_matrix.get(lang) is not None:
        doc_matrix = bm25_matrix[lang]
    else:
        doc_matrix = build_sparse_matrix(tokenized_corpus_by_lang[lang], vocab, idf_by_lang[lang], avgdl_by_lang[lang], lang)
        bm25_matrix[lang] = doc_matrix

    query_matrix = build_sparse_matrix(tokenized_queries_by_lang[lang], vocab, idf_by_lang[lang], avgdl_by_lang[lang], lang, is_query=True)
    scores_matrix = query_matrix.dot(doc_matrix.T)
    scores_matrix_lang[lang] = scores_matrix

# save bm25 matrix and idx to docid
save_data(bm25_matrix, BM25_MATRIX_PATH)
save_data(idx_to_docid, IDX_TO_DOCID_PATH)

# initialize final res matrix with dim test_data.shape[0] x k
k = 10
results_final = {}

# populate results fina;
for lang in tqdm(test_data['lang'].unique(), desc="Populating results"):
    lang_idx = test_data[test_data['lang'] == lang].index
    scores_matrix = scores_matrix_lang[lang].toarray()

    for i, idx in enumerate(lang_idx):
        scores = scores_matrix[i]
        top_k_chunk_idx = np.argsort(scores)[::-1]  # Sort chunks by score (highest first)
        
        seen_docids = set()  # Keep track of already seen original documents
        top_k_docids = []
        
        for j in top_k_chunk_idx:
            # Map chunk index back to the original document ID for the specific language
            original_docid = chunk_to_original_doc[lang][j]  # Get the original document ID
            
            # Only add the document if it's not already in the list
            if original_docid not in seen_docids:
                top_k_docids.append(original_docid)
                seen_docids.add(original_docid)
            
            # Stop once we've collected 10 unique document IDs
            if len(top_k_docids) == k:
                break
        
        results_final[idx] = top_k_docids

write_submission_csv(results_final, 'submission.csv')