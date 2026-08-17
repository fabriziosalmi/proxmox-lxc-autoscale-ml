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
        logging.info("IsolationForest model training completed.")
        return pipeline, features_to_use  # Return both the model and the feature set used
    except Exception as e:
        logging.error(f"Error during model training: {e}")
        return None, None


# IsolationForest.decision_function returns a signed distance from the decision
# boundary, positive for inliers and negative for outliers, in practice within
# roughly +/-0.5. Anything at or beyond this distance counts as full confidence.
DECISION_SCORE_SCALE = 0.5


def score_to_confidence(anomaly_score):
    """
    Map an IsolationForest decision score onto a 0-100 confidence.

    Confidence means "how far this sample is from the decision boundary", so 0
    is a borderline call and 100 is unambiguous, in either direction.

    The previous formula was `(1 - score) * 100`, which produced roughly
    50-150% -- never below 50 and not bounded by 100 -- so it could not be
    compared against a percentage threshold the way the documentation claimed.
    """
    confidence = abs(float(anomaly_score)) / DECISION_SCORE_SCALE * 100.0
    return max(0.0, min(100.0, confidence))


def predict_anomalies(model, latest_metrics, features_to_use, config):
    # Ensure only the relevant features are used for prediction
    latest_metrics_df = latest_metrics[features_to_use].to_frame().T

    logging.debug(f"Features used for prediction: {latest_metrics_df.columns.tolist()}")

    try:
        anomaly_score = model.decision_function(latest_metrics_df)
        # Convert anomaly_score to a scalar if it's an array
        anomaly_score = anomaly_score.item() if isinstance(anomaly_score, np.ndarray) else anomaly_score
        confidence = score_to_confidence(anomaly_score)
        logging.debug(f"Anomaly score: {anomaly_score}, Confidence: {confidence:.2f}%")
        prediction = model.predict(latest_metrics_df)
        prediction = prediction.item() if isinstance(prediction, np.ndarray) else prediction
        return prediction, confidence
    except Exception as e:
        logging.error(f"Error during prediction with IsolationForest: {e}")
        return None, 0
