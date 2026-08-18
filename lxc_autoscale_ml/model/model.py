from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
import logging
import numpy as np

def train_anomaly_models(df, config):
    # Select only numeric features for training, excluding non-relevant columns
    features_to_use = df.select_dtypes(include=[np.number]).columns.difference(['container_id', 'timestamp'])
    X_train = df[features_to_use]

    logging.info(f"Features used for training: {list(features_to_use)}")

    model = IsolationForest(
        contamination=config.get('model', {}).get('contamination', 0.05),
        n_estimators=config.get('model', {}).get('n_estimators', 100),
        max_samples=config.get('model', {}).get('max_samples', 64),
        random_state=config.get('model', {}).get('random_state', 42)
    )

    try:
        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('IsolationForest', model)
        ])
        pipeline.fit(X_train)
        # Keep the training-score distribution on the pipeline: score_to_confidence
        # expresses a sample's distance from the boundary as a percentile of it.
        pipeline.training_abs_scores_ = np.abs(pipeline.decision_function(X_train))
        logging.info("IsolationForest model training completed.")
        return pipeline, features_to_use  # Return both the model and the feature set used
    except Exception as e:
        logging.error(f"Error during model training: {e}")
        return None, None


def score_to_confidence(anomaly_score, training_scores=None):
    """
    Map an IsolationForest decision score onto a 0-100 confidence.

    Confidence is the percentile of this sample's distance from the decision
    boundary among the distances seen during training: 90 means "further from
    the boundary than 90% of the history this model was fitted on".

    Two earlier definitions were wrong in opposite directions. `(1 - score) *
    100` produced roughly 50-150%, so it was never below 50 and not bounded by
    100. Dividing by a hard-coded 0.5 assumed a spread about four times the
    real one -- measured `|decision_function|` tops out near 0.14 -- so
    confidence never exceeded about 27%, and any `min_confidence` above that
    silently disabled all scaling. The documented "cautious" preset used 80.

    Deriving the scale from the model's own training scores removes the
    invented constant: the full 0-100 range is reachable by construction, and
    a threshold means the same thing whatever the data looks like.
    """
    score = abs(float(anomaly_score))
    if training_scores is None or len(training_scores) == 0:
        # No reference distribution: report nothing rather than a number that
        # cannot be compared against a threshold.
        return 0.0
    return float((np.asarray(training_scores) <= score).mean() * 100.0)


def predict_anomalies(model, latest_metrics, features_to_use, config):
    # Ensure only the relevant features are used for prediction
    latest_metrics_df = latest_metrics[features_to_use].to_frame().T

    logging.debug(f"Features used for prediction: {latest_metrics_df.columns.tolist()}")

    try:
        anomaly_score = model.decision_function(latest_metrics_df)
        # Convert anomaly_score to a scalar if it's an array
        anomaly_score = anomaly_score.item() if isinstance(anomaly_score, np.ndarray) else anomaly_score
        confidence = score_to_confidence(
            anomaly_score, getattr(model, "training_abs_scores_", None))
        logging.debug(f"Anomaly score: {anomaly_score}, Confidence: {confidence:.2f}%")
        prediction = model.predict(latest_metrics_df)
        prediction = prediction.item() if isinstance(prediction, np.ndarray) else prediction
        return prediction, confidence
    except Exception as e:
        logging.error(f"Error during prediction with IsolationForest: {e}")
        return None, 0
