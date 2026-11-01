import datetime

from pydantic import BaseModel

from app.schemas.lottery import LotteryType
from app.schemas.predict import PredictResponse


class SavedPrediction(BaseModel):
    id: int
    generated_at: datetime.datetime
    model_version: str
    result: PredictResponse


class SavedPredictionList(BaseModel):
    predictions: list[SavedPrediction]


class ModelEvaluation(BaseModel):
    id: int
    lottery: LotteryType
    source_last_round: int
    source_draw_count: int
    evaluated_at: datetime.datetime
    model_version: str
    evaluated_draws: int
    actual_average_score: float
    random_average_score: float
    score_lift_percent: float
    above_random_rate: float


class ModelEvaluationList(BaseModel):
    evaluations: list[ModelEvaluation]
