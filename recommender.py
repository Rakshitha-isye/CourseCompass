"""Hybrid course recommendation engine: collaborative filtering + interest matching + popularity."""
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.decomposition import TruncatedSVD
from database import get_db

def _load_data():
    with get_db() as db:
        courses = pd.read_sql_query("SELECT * FROM courses", db)
        ratings = pd.read_sql_query("SELECT user_id, course_id, rating FROM ratings", db)
        users = pd.read_sql_query("SELECT id, interests FROM users", db)
    return courses, ratings, users

def get_popular_courses(limit=6):
    courses, ratings, _ = _load_data()
    if courses.empty:
        return []
    if not ratings.empty:
        stats = ratings.groupby("course_id")["rating"].agg(["mean", "count"]).reset_index()
        # Bayesian-style score prevents a course with only one rating from dominating.
        global_mean = float(ratings["rating"].mean())
        prior_count = 3
        stats["score"] = (stats["count"] * stats["mean"] + prior_count * global_mean) / (stats["count"] + prior_count)
        courses = courses.merge(stats[["course_id", "score"]], left_on="id", right_on="course_id", how="left")
        courses["score"] = courses["score"].fillna(courses["rating"])
        courses = courses.sort_values("score", ascending=False)
    else:
        courses = courses.sort_values("rating", ascending=False)
    return courses.head(limit).to_dict("records")

def _collaborative_scores(user_id, ratings, courses):
    """Predict ratings using user-user cosine similarity; returns {course_id: score}."""
    if ratings.empty or user_id not in ratings["user_id"].values:
        return {}
    matrix = ratings.pivot_table(index="user_id", columns="course_id", values="rating")
    # Similarity is computed after mean-centering each user's observed ratings.
    user_means = matrix.mean(axis=1)
    centered = matrix.sub(user_means, axis=0).fillna(0)
    similarities = cosine_similarity(centered)
    sim_df = pd.DataFrame(similarities, index=matrix.index, columns=matrix.index)
    if user_id not in sim_df.index:
        return {}
    target_sims = sim_df.loc[user_id].drop(index=user_id, errors="ignore")
    user_ratings = matrix.loc[user_id]
    scores = {}
    for course_id in matrix.columns:
        if pd.notna(user_ratings.get(course_id)):
            continue
        column = matrix[course_id]
        valid = column.dropna()
        if valid.empty:
            continue
        weights = target_sims.reindex(valid.index).fillna(0)
        denominator = float(weights.abs().sum())
        if denominator == 0:
            continue
        target_mean = float(user_means.loc[user_id])
        deviations = valid - user_means.reindex(valid.index)
        scores[int(course_id)] = target_mean + float((weights * deviations).sum()) / denominator
    return scores

def _svd_scores(user_id, ratings):
    """Optional low-rank matrix-factorization estimates from a small ratings matrix."""
    if ratings.empty or ratings["user_id"].nunique() < 2 or ratings["course_id"].nunique() < 2:
        return {}
    matrix = ratings.pivot_table(index="user_id", columns="course_id", values="rating")
    # Mean-impute missing values for a compact demonstration; real deployments should
    # evaluate alternative implicit/explicit-feedback matrix factorization approaches.
    filled = matrix.fillna(matrix.mean(axis=0)).fillna(ratings["rating"].mean())
    n_components = min(2, filled.shape[0] - 1, filled.shape[1] - 1)
    if n_components < 1 or user_id not in filled.index:
        return {}
    try:
        model = TruncatedSVD(n_components=n_components, random_state=42)
        latent = model.fit_transform(filled)
        reconstructed = latent @ model.components_
        estimates = pd.DataFrame(reconstructed, index=filled.index, columns=filled.columns)
        return {int(cid): float(estimates.loc[user_id, cid])
                for cid in matrix.columns if pd.isna(matrix.loc[user_id, cid])}
    except (ValueError, np.linalg.LinAlgError):
        return {}

def get_recommendation_reason(course, interests, cf_score=None):
    category = str(course.get("category", ""))
    interest_set = {x.strip().lower() for x in (interests or "").split(",") if x.strip()}
    if category.lower() in interest_set:
        return f"Matches your interest in {category}."
    if cf_score is not None:
        return "Suggested from ratings by learners with similar course preferences."
    return "Popular course you may want to explore."

def recommend_courses(user_id, limit=6):
    courses, ratings, users = _load_data()
    if courses.empty:
        return []
    user_row = users[users["id"] == user_id]
    interests = user_row.iloc[0]["interests"] if not user_row.empty else ""
    rated_ids = set(ratings.loc[ratings["user_id"] == user_id, "course_id"].astype(int).tolist())
    cf_scores = _collaborative_scores(user_id, ratings, courses)
    svd_scores = _svd_scores(user_id, ratings)
    global_mean = float(ratings["rating"].mean()) if not ratings.empty else 3.5
    scored = []
    for course in courses.to_dict("records"):
        cid = int(course["id"])
        if cid in rated_ids:
            continue
        category = str(course["category"]).lower()
        interest_set = {x.strip().lower() for x in (interests or "").split(",") if x.strip()}
        interest_score = 1.0 if category in interest_set else 0.0
        cf = cf_scores.get(cid)
        svd = svd_scores.get(cid)
        # Normalize each signal to a comparable 0..1-ish scale.
        cf_signal = ((cf - 1) / 4) if cf is not None else None
        svd_signal = ((svd - 1) / 4) if svd is not None else None
        popularity_signal = float(course.get("rating", 0) or 0) / 5
        signals = []
        weights = []
        if cf_signal is not None:
            signals.append(max(0, min(1, cf_signal))); weights.append(0.45)
        if svd_signal is not None:
            signals.append(max(0, min(1, svd_signal))); weights.append(0.20)
        signals.extend([interest_score, popularity_signal])
        weights.extend([0.25, 0.10])
        score = sum(s*w for s,w in zip(signals, weights)) / sum(weights)
        course["recommendation_score"] = round(score, 3)
        course["recommendation_reason"] = get_recommendation_reason(course, interests, cf)
        scored.append(course)
    # If every course has been rated, still show highest-rated courses as a fallback.
    scored.sort(key=lambda x: (x["recommendation_score"], x["rating"]), reverse=True)
    if not scored:
        return get_popular_courses(limit)
    return scored[:limit]
