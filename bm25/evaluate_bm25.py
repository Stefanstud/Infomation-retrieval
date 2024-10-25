import json
import pandas as pd
from bm25 import BM25ChunkRetriever
from bm25 import BM25ChunkRetriever

def evaluate_retrieval(queries, corpus, retriever):
    """
    Evaluate retrieval performance per language
    """
    results = retriever.retrieve(queries, corpus)

    results_per_lang = {}
    for lang, lang_data in queries.groupby('lang'):
        recall_at_1 = 0
        top_10_accuracy = 0
        total_queries = len(lang_data)

        for i, row in lang_data.iterrows():
            positive_doc = row['positive_docs']
            predicted_docs = results[i]

            if positive_doc == predicted_docs[0]:
                recall_at_1 += 1
            if positive_doc in predicted_docs:
                top_10_accuracy += 1

        results_per_lang[lang] = {
            'recall_at_1': recall_at_1 / total_queries,
            'top_10_accuracy': top_10_accuracy / total_queries
        }

        # add average recall and top-10 accuracy
        results_per_lang['average'] = {
            'recall_at_1': sum([v['recall_at_1'] for v in results_per_lang.values()]) / len(results_per_lang),
            'top_10_accuracy': sum([v['top_10_accuracy'] for v in results_per_lang.values()]) / len(results_per_lang)
        }

    return results_per_lang

def main():
    with open('../data/corpus.json', 'r', encoding='utf-8') as f:
        corpus = json.load(f)

    dev_data = pd.read_csv('../data/dev.csv')
    
    retriever = BM25ChunkRetriever(
        stopwords_path='../data/stopwords-ko.txt'
    )
    # do hyperparameter tuning k1 from [0.5-2.0] increments of 0.1 or 0.2; b from [0.0-1.0] increments of 0.1
    results = evaluate_retrieval(dev_data, corpus, retriever)

    print("\nBM25 Results per Language:")
    print(pd.DataFrame(results).T)

if __name__ == "__main__":
    main()