#!/usr/bin/env python3
"""
Performance Prediction System for Anime Generation
Uses machine learning to predict generation times and identify bottlenecks.
"""

import logging
import pickle
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.neural_network import MLPRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.feature_selection import SelectKBest, f_regression
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

class PerformancePredictor:
    """ML-based performance prediction system for anime generation"""

    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.models = {}
        self.scalers = {}
        self.feature_selectors = {}
        self.label_encoders = {}

        # Model configurations with hyperparameters
        self.model_configs = {
            'random_forest': {
                'model_class': RandomForestRegressor,
                'params': {
                    'n_estimators': 100,
                    'max_depth': 10,
                    'random_state': 42,
                    'n_jobs': -1
                }
            },
            'gradient_boosting': {
                'model_class': GradientBoostingRegressor,
                'params': {
                    'n_estimators': 100,
                    'learning_rate': 0.1,
                    'max_depth': 6,
                    'random_state': 42
                }
            },
            'linear_regression': {
                'model_class': LinearRegression,
                'params': {}
            },
            'neural_network': {
                'model_class': MLPRegressor,
                'params': {
                    'hidden_layer_sizes': (100, 50),
                    'max_iter': 1000,
                    'random_state': 42,
                    'early_stopping': True
                }
            }
        }

    def connect_db(self):
        """Create database connection"""
        return psycopg2.connect(
            host=self.db_config['host'],
            port=self.db_config['port'],
            database=self.db_config['database'],
            user=self.db_config['user'],
            password=self.db_config['password']
        )

    def extract_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract and engineer features for ML prediction"""
        features = df.copy()

        # Handle resolution
        if 'resolution' in features.columns:
            features['width'] = features['resolution'].str.extract(r'(\d+)x\d+').astype(float)
            features['height'] = features['resolution'].str.extract(r'\d+x(\d+)').astype(float)
            features['resolution_pixels'] = features['width'] * features['height']
            features.drop(['resolution', 'width', 'height'], axis=1, inplace=True, errors='ignore')

        # Time-based features
        if 'created_at' in features.columns:
            features['created_at'] = pd.to_datetime(features['created_at'])
            features['hour'] = features['created_at'].dt.hour
            features['day_of_week'] = features['created_at'].dt.dayofweek
            features['is_weekend'] = (features['day_of_week'] >= 5).astype(int)
            features.drop(['created_at'], axis=1, inplace=True)

        # Computational complexity features
        if 'frame_count' in features.columns and 'steps' in features.columns:
            features['total_computation'] = features['frame_count'] * features['steps'].fillna(20)

        # GPU efficiency features
        if 'gpu_utilization_avg' in features.columns and 'vram_used_mb' in features.columns:
            features['gpu_efficiency'] = (features['gpu_utilization_avg'] *
                                        features['vram_used_mb']).fillna(0)

        # Handle categorical variables
        categorical_columns = ['pipeline_type', 'job_type', 'gpu_model', 'model_version']
        for col in categorical_columns:
            if col in features.columns:
                if col not in self.label_encoders:
                    self.label_encoders[col] = LabelEncoder()
                    # Fit on all unique values including new ones
                    unique_vals = features[col].dropna().astype(str).unique()
                    self.label_encoders[col].fit(unique_vals)

                # Transform data
                features[col] = features[col].fillna('unknown').astype(str)
                # Handle unseen categories
                known_categories = set(self.label_encoders[col].classes_)
                features[col] = features[col].apply(
                    lambda x: x if x in known_categories else 'unknown'
                )
                features[col] = self.label_encoders[col].transform(features[col])

        # Fill missing values
        numeric_columns = features.select_dtypes(include=[np.number]).columns
        features[numeric_columns] = features[numeric_columns].fillna(
            features[numeric_columns].median()
        )

        return features

    def get_training_data(self, pipeline_type: str = None,
                         days_back: int = 30) -> pd.DataFrame:
        """Fetch training data from database"""
        with self.connect_db() as conn:
            query = """
            SELECT * FROM anime_api.ml_training_data
            WHERE total_time_seconds IS NOT NULL
            AND total_time_seconds > 0
            AND created_at >= %s
            """
            params = [datetime.now() - timedelta(days=days_back)]

            if pipeline_type:
                query += " AND pipeline_type = %s"
                params.append(pipeline_type)

            query += " ORDER BY created_at DESC"

            df = pd.read_sql(query, conn, params=params)
            return df

    def train_model(self, pipeline_type: str, model_type: str = 'random_forest') -> Dict:
        """Train prediction model for specific pipeline type"""
        logger.info(f"Training {model_type} model for {pipeline_type} pipeline")

        # Get training data
        df = self.get_training_data(pipeline_type)

        if len(df) < 10:
            raise ValueError(f"Insufficient training data for {pipeline_type}: {len(df)} samples")

        # Prepare features
        target_col = 'total_time_seconds'
        feature_cols = [col for col in df.columns if col != target_col and col != 'id']

        X = self.extract_features(df[feature_cols])
        y = df[target_col]

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )

        # Feature scaling
        scaler_key = f"{pipeline_type}_{model_type}"
        self.scalers[scaler_key] = StandardScaler()
        X_train_scaled = self.scalers[scaler_key].fit_transform(X_train)
        X_test_scaled = self.scalers[scaler_key].transform(X_test)

        # Feature selection
        self.feature_selectors[scaler_key] = SelectKBest(
            score_func=f_regression, k=min(10, X_train.shape[1])
        )
        X_train_selected = self.feature_selectors[scaler_key].fit_transform(X_train_scaled, y_train)
        X_test_selected = self.feature_selectors[scaler_key].transform(X_test_scaled)

        # Train model
        model_config = self.model_configs[model_type]
        model = model_config['model_class'](**model_config['params'])
        model.fit(X_train_selected, y_train)

        # Evaluate model
        y_pred = model.predict(X_test_selected)

        metrics = {
            'mean_absolute_error': mean_absolute_error(y_test, y_pred),
            'mean_squared_error': mean_squared_error(y_test, y_pred),
            'r2_score': r2_score(y_test, y_pred),
            'accuracy_within_20_percent': np.mean(
                np.abs(y_pred - y_test) / y_test <= 0.2
            ) * 100
        }

        # Cross validation
        cv_scores = cross_val_score(
            model, X_train_selected, y_train, cv=5, scoring='neg_mean_absolute_error'
        )
        metrics['cv_mean_absolute_error'] = -cv_scores.mean()
        metrics['cv_std'] = cv_scores.std()

        # Store model
        model_key = f"{pipeline_type}_{model_type}"
        self.models[model_key] = {
            'model': model,
            'metrics': metrics,
            'feature_columns': X.columns.tolist(),
            'trained_at': datetime.now(),
            'training_samples': len(X_train)
        }

        logger.info(f"Model trained successfully. MAE: {metrics['mean_absolute_error']:.2f}s, "
                   f"R²: {metrics['r2_score']:.3f}, "
                   f"Accuracy ±20%: {metrics['accuracy_within_20_percent']:.1f}%")

        return metrics

    def predict_generation_time(self, job_params: Dict) -> Dict:
        """Predict generation time for given job parameters"""
        pipeline_type = job_params.get('pipeline_type', 'image')

        # Try different model types, prefer the best performing one
        model_types = ['random_forest', 'gradient_boosting', 'linear_regression']

        predictions = {}
        confidence_scores = {}

        for model_type in model_types:
            model_key = f"{pipeline_type}_{model_type}"

            if model_key not in self.models:
                continue

            try:
                # Prepare input features
                input_df = pd.DataFrame([job_params])
                X = self.extract_features(input_df)

                # Ensure all required features are present
                model_features = self.models[model_key]['feature_columns']
                for feature in model_features:
                    if feature not in X.columns:
                        X[feature] = 0  # Default value for missing features

                X = X[model_features]  # Ensure correct order and columns

                # Scale and select features
                scaler_key = model_key
                if scaler_key in self.scalers:
                    X_scaled = self.scalers[scaler_key].transform(X)
                    X_selected = self.feature_selectors[scaler_key].transform(X_scaled)
                else:
                    X_selected = X

                # Make prediction
                model = self.models[model_key]['model']
                prediction = model.predict(X_selected)[0]

                # Calculate confidence based on model performance
                metrics = self.models[model_key]['metrics']
                confidence = max(0, 1 - (metrics['mean_absolute_error'] / prediction))

                predictions[model_type] = max(1.0, prediction)  # Minimum 1 second
                confidence_scores[model_type] = confidence

            except Exception as e:
                logger.warning(f"Failed to predict with {model_type}: {e}")
                continue

        if not predictions:
            # Fallback prediction based on complexity
            frame_count = job_params.get('frame_count', 1)
            resolution = job_params.get('resolution', '512x512')
            steps = job_params.get('steps', 20)

            # Simple heuristic
            if pipeline_type == 'video':
                base_time = frame_count * 5.0  # 5 seconds per frame
            else:
                base_time = 30.0  # 30 seconds for image

            # Adjust for resolution
            if 'x' in str(resolution):
                try:
                    w, h = map(int, str(resolution).split('x'))
                    pixels = w * h
                    resolution_factor = pixels / (512 * 512)  # Normalize to 512x512
                    base_time *= resolution_factor
                except:
                    pass

            # Adjust for steps
            base_time *= (steps / 20.0)  # Normalize to 20 steps

            return {
                'predicted_time_seconds': max(1.0, base_time),
                'confidence': 0.3,
                'prediction_method': 'heuristic',
                'model_used': 'fallback',
                'uncertainty_range': [base_time * 0.5, base_time * 2.0]
            }

        # Use the best performing model
        best_model = max(confidence_scores.keys(), key=lambda k: confidence_scores[k])
        best_prediction = predictions[best_model]
        best_confidence = confidence_scores[best_model]

        # Calculate uncertainty range based on model performance
        model_key = f"{pipeline_type}_{best_model}"
        mae = self.models[model_key]['metrics']['mean_absolute_error']

        return {
            'predicted_time_seconds': best_prediction,
            'confidence': best_confidence,
            'prediction_method': 'ml_model',
            'model_used': best_model,
            'uncertainty_range': [
                max(1.0, best_prediction - mae * 1.5),
                best_prediction + mae * 1.5
            ],
            'all_predictions': predictions
        }

    def analyze_performance_trends(self, days_back: int = 7) -> Dict:
        """Analyze recent performance trends and identify bottlenecks"""
        with self.connect_db() as conn:
            # Get recent performance data
            query = """
            SELECT
                pipeline_type,
                DATE(created_at) as date,
                AVG(total_time_seconds) as avg_time,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY total_time_seconds) as median_time,
                MIN(total_time_seconds) as min_time,
                MAX(total_time_seconds) as max_time,
                AVG(gpu_utilization_avg) as avg_gpu_util,
                AVG(cpu_utilization_avg) as avg_cpu_util,
                COUNT(*) as job_count,
                COUNT(CASE WHEN error_details::text != '{}' THEN 1 END) as error_count
            FROM anime_api.generation_performance
            WHERE created_at >= %s
            GROUP BY pipeline_type, DATE(created_at)
            ORDER BY date DESC, pipeline_type
            """

            df = pd.read_sql(query, conn, params=[datetime.now() - timedelta(days=days_back)])

            if df.empty:
                return {'message': 'No performance data available for analysis'}

            analysis = {}

            for pipeline_type in df['pipeline_type'].unique():
                pipeline_data = df[df['pipeline_type'] == pipeline_type]

                # Calculate trends
                avg_times = pipeline_data['avg_time'].values
                if len(avg_times) > 1:
                    trend_slope = np.polyfit(range(len(avg_times)), avg_times, 1)[0]
                else:
                    trend_slope = 0

                # Identify bottlenecks
                bottlenecks = []
                avg_gpu_util = pipeline_data['avg_gpu_util'].mean()
                avg_cpu_util = pipeline_data['avg_cpu_util'].mean()

                if avg_gpu_util < 60:
                    bottlenecks.append('low_gpu_utilization')
                if avg_cpu_util > 80:
                    bottlenecks.append('high_cpu_usage')

                success_rate = 1 - (pipeline_data['error_count'].sum() /
                                  pipeline_data['job_count'].sum())
                if success_rate < 0.9:
                    bottlenecks.append('high_failure_rate')

                analysis[pipeline_type] = {
                    'avg_generation_time': float(pipeline_data['avg_time'].mean()),
                    'median_generation_time': float(pipeline_data['median_time'].mean()),
                    'time_trend': 'increasing' if trend_slope > 0 else 'decreasing' if trend_slope < 0 else 'stable',
                    'trend_slope_per_day': float(trend_slope),
                    'success_rate': float(success_rate),
                    'avg_gpu_utilization': float(avg_gpu_util),
                    'avg_cpu_utilization': float(avg_cpu_util),
                    'total_jobs': int(pipeline_data['job_count'].sum()),
                    'bottlenecks': bottlenecks,
                    'recommendations': self._generate_recommendations(bottlenecks, avg_gpu_util, avg_cpu_util)
                }

            return analysis

    def _generate_recommendations(self, bottlenecks: List[str],
                                gpu_util: float, cpu_util: float) -> List[str]:
        """Generate performance improvement recommendations"""
        recommendations = []

        if 'low_gpu_utilization' in bottlenecks:
            recommendations.append(
                f"GPU utilization is low ({gpu_util:.1f}%). Consider increasing batch size or using a more complex model."
            )

        if 'high_cpu_usage' in bottlenecks:
            recommendations.append(
                f"CPU usage is high ({cpu_util:.1f}%). Consider optimizing preprocessing or reducing CPU-intensive operations."
            )

        if 'high_failure_rate' in bottlenecks:
            recommendations.append(
                "High failure rate detected. Review error logs and consider adjusting generation parameters."
            )

        if not bottlenecks:
            recommendations.append("Performance is optimal. No immediate improvements needed.")

        return recommendations

    def save_model_to_db(self, pipeline_type: str, model_type: str):
        """Save trained model to database for persistence"""
        model_key = f"{pipeline_type}_{model_type}"

        if model_key not in self.models:
            raise ValueError(f"Model {model_key} not found")

        model_data = self.models[model_key]

        # Serialize model and supporting objects
        model_blob = pickle.dumps({
            'model': model_data['model'],
            'scaler': self.scalers.get(model_key),
            'feature_selector': self.feature_selectors.get(model_key),
            'label_encoders': {k: v for k, v in self.label_encoders.items()}
        })

        with self.connect_db() as conn:
            with conn.cursor() as cursor:
                # Deactivate old models
                cursor.execute("""
                    UPDATE anime_api.performance_prediction_models
                    SET is_active = FALSE
                    WHERE pipeline_type = %s AND model_type = %s
                """, (pipeline_type, model_type))

                # Insert new model
                cursor.execute("""
                    INSERT INTO anime_api.performance_prediction_models
                    (model_name, model_type, pipeline_type, model_data, feature_columns,
                     accuracy_score, mean_absolute_error, training_data_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    f"{pipeline_type}_{model_type}_{datetime.now().strftime('%Y%m%d')}",
                    model_type,
                    pipeline_type,
                    model_blob,
                    json.dumps(model_data['feature_columns']),
                    model_data['metrics'].get('accuracy_within_20_percent'),
                    model_data['metrics']['mean_absolute_error'],
                    model_data['training_samples']
                ))

                conn.commit()

        logger.info(f"Model {model_key} saved to database")

    def load_model_from_db(self, pipeline_type: str, model_type: str):
        """Load trained model from database"""
        with self.connect_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT model_data, feature_columns, accuracy_score, mean_absolute_error
                    FROM anime_api.performance_prediction_models
                    WHERE pipeline_type = %s AND model_type = %s AND is_active = TRUE
                    ORDER BY last_trained_at DESC
                    LIMIT 1
                """, (pipeline_type, model_type))

                row = cursor.fetchone()
                if not row:
                    return False

                # Deserialize model
                model_obj = pickle.loads(row['model_data'])

                model_key = f"{pipeline_type}_{model_type}"
                self.models[model_key] = {
                    'model': model_obj['model'],
                    'feature_columns': json.loads(row['feature_columns']),
                    'metrics': {
                        'accuracy_within_20_percent': row['accuracy_score'],
                        'mean_absolute_error': row['mean_absolute_error']
                    }
                }

                # Restore supporting objects
                if 'scaler' in model_obj and model_obj['scaler']:
                    self.scalers[model_key] = model_obj['scaler']

                if 'feature_selector' in model_obj and model_obj['feature_selector']:
                    self.feature_selectors[model_key] = model_obj['feature_selector']

                if 'label_encoders' in model_obj:
                    self.label_encoders.update(model_obj['label_encoders'])

                logger.info(f"Model {model_key} loaded from database")
                return True