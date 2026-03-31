# src/ml_scorer.py
#
# WHY THIS FILE EXISTS:
# Our current scorer uses hardcoded weights:
#   token_overlap: 0.30
#   levenshtein:   0.25
#   embedding:     0.10
#
# These weights are our best guess — not learned from data.
# A machine learning model learns the OPTIMAL weights
# directly from labelled analyst decisions.
#
# WHAT CHANGES:
# Before ML: we decide weights based on intuition
# After ML:  data decides weights based on evidence
#
# WHY LOGISTIC REGRESSION:
# Simple, fast, explainable.
# Compliance requires explainability — we must show
# regulators WHY the system made each decision.
# Logistic regression coefficients ARE the explanation.
# Neural networks are black boxes — unacceptable in compliance.
#
# THE PIPELINE:
# 1. Extract feature vectors from record pairs
# 2. Generate training labels from ground truth
# 3. Train logistic regression model
# 4. Compare ML weights vs our hardcoded weights
# 5. Evaluate ML model precision and recall
# 6. Save model for reuse

import sys
import os
import json
import pickle

sys.path.append(os.path.dirname(__file__))
sys.path.append(
    os.path.join(os.path.dirname(__file__), '..', 'data')
)

from sanctions import (
    levenshtein_similarity,
    phonetic_similarity,
    jaccard_similarity,
    token_overlap_similarity,
    embedding_similarity,
    score_dob,
    score_country,
    score_passport,
)
from synthetic_sanctions import (
    SANCTIONS_RECORDS,
    GROUND_TRUTH_CLUSTERS,
)

from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    classification_report,
)
import numpy as np


# ============================================================
# STEP 1 — FEATURE EXTRACTION
# ============================================================

def extract_features(record1, record2):
    """
    Converts two records into a feature vector —
    a list of 8 numbers that the ML model uses.

    WHY 8 FEATURES:
    Each number captures one aspect of similarity.
    Together they give the model a complete picture
    of how similar two records are.

    Feature vector structure:
    [0] levenshtein_score    — character edit distance
    [1] phonetic_score       — sound similarity
    [2] token_overlap_score  — shared words
    [3] ngram_score          — character chunk overlap
    [4] embedding_score      — semantic similarity
    [5] dob_score            — date of birth proximity
    [6] country_score        — country match
    [7] passport_score       — passport match

    WHY THIS IS IMPORTANT:
    The feature vector is the LANGUAGE the ML model speaks.
    It cannot read names or dates directly.
    We translate human-readable records into numbers
    that the model can learn from.

    NULL handling:
    Missing fields become -1 in the feature vector.
    WHY -1 not 0:
    0 means "no match" — a real score.
    -1 means "unknown" — no data available.
    The model learns to treat -1 differently from 0.
    """
    name1    = record1.get('name', '') or ''
    name2    = record2.get('name', '') or ''
    aliases1 = record1.get('aliases', []) or []
    aliases2 = record2.get('aliases', []) or []

    # Build all name combinations including aliases
    all_names1 = [name1] + aliases1 if name1 else aliases1
    all_names2 = [name2] + aliases2 if name2 else aliases2

    # Get best name score across all combinations
    best_lev      = 0.0
    best_phonetic = 0.0
    best_token    = 0.0
    best_ngram    = 0.0
    best_embed    = 0.0

    for n1 in all_names1:
        for n2 in all_names2:
            if n1 and n2:
                best_lev = max(
                    best_lev,
                    levenshtein_similarity(n1, n2)
                )
                best_phonetic = max(
                    best_phonetic,
                    phonetic_similarity(n1, n2)
                )
                best_token = max(
                    best_token,
                    token_overlap_similarity(n1, n2)
                )
                best_ngram = max(
                    best_ngram,
                    jaccard_similarity(n1, n2)
                )
                best_embed = max(
                    best_embed,
                    embedding_similarity(n1, n2)
                )

    # Score other fields
    dob_score_val = score_dob(
        record1.get('dob'),
        record2.get('dob')
    )
    country_score_val = score_country(
        record1.get('country'),
        record2.get('country')
    )
    passport_score_val = score_passport(
        record1.get('passport'),
        record2.get('passport')
    )

    # Convert None to -1
    # WHY: sklearn cannot handle None values
    # -1 signals to the model: this field was missing
    dob_feature      = dob_score_val      if dob_score_val      is not None else -1
    country_feature  = country_score_val  if country_score_val  is not None else -1
    passport_feature = passport_score_val if passport_score_val is not None else -1

    return [
        best_lev,        # feature 0
        best_phonetic,   # feature 1
        best_token,      # feature 2
        best_ngram,      # feature 3
        best_embed,      # feature 4
        dob_feature,     # feature 5
        country_feature, # feature 6
        passport_feature # feature 7
    ]


# ============================================================
# STEP 2 — GENERATE TRAINING DATA
# ============================================================

def generate_training_data(records, ground_truth_clusters):
    """
    Generates labelled training data from our synthetic dataset.

    For every possible pair of records:
    - Extract feature vector
    - Assign label: 1 = same person, 0 = different people

    WHY ALL PAIRS:
    The model needs to see both positive examples (matches)
    and negative examples (non-matches) to learn the boundary
    between them.

    In real production:
    Labels come from analyst decisions in the review queue.
    500 confirmed matches + 200 rejections = 700 training rows.
    Here we generate labels from our ground truth clusters.

    Returns:
    X: list of feature vectors (one per pair)
    y: list of labels (1 or 0)
    pair_info: list of (id1, id2) for debugging
    """
    # Build set of true match pairs for quick lookup
    true_pairs = set()
    for cluster in ground_truth_clusters:
        cluster_list = list(cluster)
        for i in range(len(cluster_list)):
            for j in range(i+1, len(cluster_list)):
                pair = tuple(sorted(
                    [cluster_list[i], cluster_list[j]]
                ))
                true_pairs.add(pair)

    X          = []   # feature vectors
    y          = []   # labels
    pair_info  = []   # for debugging

    records_by_id = {r['id']: r for r in records}

    # Generate all possible pairs
    n = len(records)
    for i in range(n):
        for j in range(i+1, n):
            r1 = records[i]
            r2 = records[j]

            pair = tuple(sorted([r1['id'], r2['id']]))

            # Extract features
            features = extract_features(r1, r2)

            # Assign label
            label = 1 if pair in true_pairs else 0

            X.append(features)
            y.append(label)
            pair_info.append(pair)

    return X, y, pair_info


# ============================================================
# STEP 3 — TRAIN THE MODEL
# ============================================================

def train_model(X, y):
    """
    Trains a logistic regression classifier.

    WHY LOGISTIC REGRESSION:
    - Simple and fast
    - Outputs probability between 0 and 1
    - Coefficients are interpretable as feature weights
    - Compliance teams can inspect and explain decisions
    - Works well even with small datasets like ours

    WHY NOT RANDOM FOREST OR NEURAL NETWORK:
    - Black box — cannot explain individual decisions
    - Compliance regulators require explainability
    - Overkill for 8 features

    Parameters:
    class_weight='balanced' — WHY:
    We have more non-matches than matches (12 vs 178).
    Without balancing, model learns to always predict 0.
    Balanced weighting makes the model treat both classes
    equally regardless of how many examples each has.

    This is critical for sanctions — we care deeply
    about the minority class (true matches).
    """
    model = LogisticRegression(
        class_weight='balanced',
        max_iter=1000,
        random_state=42
    )
    model.fit(X, y)
    return model


# ============================================================
# STEP 4 — INTERPRET THE MODEL
# ============================================================

def print_model_weights(model):
    """
    Prints what the model learned about each feature.

    WHY THIS MATTERS:
    The coefficients tell us which features the model
    found most important for distinguishing matches
    from non-matches.

    We compare these to our hardcoded weights to see
    what we got right and what we got wrong.

    Positive coefficient: higher score → more likely match
    Negative coefficient: higher score → less likely match
    Large magnitude: feature is very important
    Near zero: feature is not very useful
    """
    feature_names = [
        'levenshtein',
        'phonetic',
        'token_overlap',
        'ngram',
        'embedding',
        'dob_score',
        'country_score',
        'passport_score',
    ]

    coefficients = model.coef_[0]

    print("LEARNED FEATURE WEIGHTS:")
    print()
    print(f"  {'Feature':20} {'Our Weight':12} {'ML Weight':12} {'Difference'}")
    print(f"  {'-'*20} {'-'*12} {'-'*12} {'-'*10}")

    # Our hardcoded weights for comparison
    our_weights = {
        'levenshtein':    0.25,
        'phonetic':       0.20,
        'token_overlap':  0.30,
        'ngram':          0.15,
        'embedding':      0.10,
        'dob_score':      0.20,
        'country_score':  0.15,
        'passport_score': 0.25,
    }

    # Normalise ML coefficients to 0-1 range for comparison
    # WHY: logistic regression coefficients are not
    # bounded to 0-1 like our weights
    # We normalise so the comparison makes sense
    abs_coefs    = np.abs(coefficients)
    total        = abs_coefs.sum()
    norm_coefs   = abs_coefs / total if total > 0 else abs_coefs

    for i, name in enumerate(feature_names):
        our_w = our_weights.get(name, 0)
        ml_w  = norm_coefs[i]
        diff  = ml_w - our_w
        arrow = "↑" if diff > 0.02 else "↓" if diff < -0.02 else "→"
        print(f"  {name:20} {our_w:12.2f} {ml_w:12.2f}"
              f" {arrow} {diff:+.2f}")


# ============================================================
# STEP 5 — EVALUATE THE MODEL
# ============================================================

def evaluate_model(model, X_test, y_test, pair_info_test):
    """
    Evaluates model performance on test data.

    WHY SEPARATE TEST SET:
    If we evaluate on the same data we trained on,
    the model looks perfect — but it just memorised
    the training data.

    A separate test set shows real performance on
    data the model has never seen.

    This is called the train/test split.
    80% for training, 20% for testing.
    """
    # Get predictions
    y_pred      = model.predict(X_test)
    y_pred_prob = model.predict_proba(X_test)[:, 1]

    precision = precision_score(y_test, y_pred,
                                zero_division=0)
    recall    = recall_score(y_test, y_pred,
                             zero_division=0)
    f1        = f1_score(y_test, y_pred,
                         zero_division=0)

    print(f"  Precision: {precision:.2f}")
    print(f"  Recall:    {recall:.2f}")
    print(f"  F1 Score:  {f1:.2f}")

    # Show any missed matches — most critical
    missed = []
    for i, (true, pred) in enumerate(zip(y_test, y_pred)):
        if true == 1 and pred == 0:
            missed.append(pair_info_test[i])

    if missed:
        print()
        print(f"  ⚠️  Missed matches: {len(missed)}")
        for pair in missed:
            print(f"     {pair}")
    else:
        print()
        print(f"  ✅ No missed matches")

    return precision, recall, f1


# ============================================================
# STEP 6 — SAVE THE MODEL
# ============================================================

def save_model(model, filepath="data/ml_scorer.pkl"):
    """
    Saves the trained model to disk.

    WHY SAVE:
    Training takes time. We do not want to retrain
    every time the system starts.
    We train once — save — load when needed.

    WHY PICKLE:
    Pickle is Python's built-in serialisation format.
    It converts a Python object into bytes that can
    be written to a file and read back later.

    In production: use joblib instead of pickle
    joblib is faster for large numpy arrays.
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'wb') as f:
        pickle.dump(model, f)
    print(f"Model saved to: {filepath}")


def load_model(filepath="data/ml_scorer.pkl"):
    """Loads a previously trained model from disk."""
    with open(filepath, 'rb') as f:
        model = pickle.load(f)
    return model


def ml_score(model, record1, record2):
    """
    Uses the trained ML model to score two records.

    Returns:
    - probability: 0.0 to 1.0 (match confidence)
    - decision: AUTO BLOCK / MANUAL REVIEW / CLEAR
    - features: the feature vector used

    WHY RETURN FEATURES:
    Explainability — we can show the analyst exactly
    which features drove the model's decision.
    """
    features = extract_features(record1, record2)
    features_array = np.array(features).reshape(1, -1)

    # predict_proba returns [prob_not_match, prob_match]
    probability = model.predict_proba(
        features_array
    )[0][1]

    # Decision thresholds
    if probability >= 0.85:
        decision = "AUTO BLOCK"
    elif probability >= 0.65:
        decision = "MANUAL REVIEW"
    else:
        decision = "CLEAR"

    return probability, decision, features


# ============================================================
# MAIN — TRAIN, EVALUATE, COMPARE
# ============================================================

if __name__ == "__main__":

    print("=" * 55)
    print("ML SCORER — TRAINING PIPELINE")
    print("=" * 55)

    # Step 1: Generate training data
    print()
    print("Step 1: Generating training data...")
    X, y, pair_info = generate_training_data(
        SANCTIONS_RECORDS, GROUND_TRUTH_CLUSTERS
    )
    print(f"  Total pairs:     {len(X)}")
    print(f"  True matches:    {sum(y)}")
    print(f"  Non-matches:     {len(y) - sum(y)}")

    # Step 2: Train/test split
    print()
    print("Step 2: Splitting into train and test sets...")
    print("  80% training, 20% testing")
    print("  WHY: evaluate on data model never saw")

    X_train, X_test, y_train, y_test, pairs_train, pairs_test = \
        train_test_split(
            X, y, pair_info,
            test_size=0.2,
            random_state=42,
            stratify=y  # WHY: keep match ratio same in both sets
        )

    print(f"  Training pairs:  {len(X_train)}")
    print(f"  Test pairs:      {len(X_test)}")

    # Step 3: Train model
    print()
    print("Step 3: Training logistic regression model...")
    model = train_model(X_train, y_train)
    print("  Model trained successfully")

    # Step 4: Print learned weights
    print()
    print("=" * 55)
    print("WHAT THE MODEL LEARNED")
    print("=" * 55)
    print()
    print_model_weights(model)

    # Step 5: Evaluate
    print()
    print("=" * 55)
    print("MODEL PERFORMANCE ON TEST SET")
    print("=" * 55)
    print()
    precision, recall, f1 = evaluate_model(
        model, X_test, y_test, pairs_test
    )

    # Step 6: Save model
    print()
    print("=" * 55)
    print("SAVING MODEL")
    print("=" * 55)
    print()
    save_model(model)

    # Step 7: Demo — score a pair with ML model
    print()
    print("=" * 55)
    print("DEMO — ML SCORING")
    print("=" * 55)
    print()

    records_by_id = {r['id']: r for r in SANCTIONS_RECORDS}
    r1 = records_by_id["OFAC-001"]
    r2 = records_by_id["UN-001"]

    prob, decision, features = ml_score(model, r1, r2)

    feature_names = [
        'levenshtein', 'phonetic', 'token_overlap',
        'ngram', 'embedding', 'dob', 'country', 'passport'
    ]

    print(f"Comparing:")
    print(f"  {r1['name']} ({r1['source']})")
    print(f"  {r2['name']} ({r2['source']})")
    print()
    print(f"Feature vector:")
    for name, value in zip(feature_names, features):
        bar = "█" * int(value * 20) if value > 0 else ""
        print(f"  {name:15} {value:5.2f}  {bar}")
    print()
    print(f"ML probability: {prob:.4f}")
    print(f"Decision:       {decision}")

    print()
    print("=" * 55)
    print("COMPLIANCE ASSESSMENT")
    print("=" * 55)
    if recall >= 0.99:
        print(f"✅ RECALL: {recall:.2f} — safe to deploy")
    else:
        print(f"❌ RECALL: {recall:.2f} — NOT safe to deploy")
        print(f"   Recall must be >= 0.99 for compliance")
        print(f"   Collect more training data first")