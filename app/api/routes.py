import datetime

from fastapi import APIRouter, HTTPException, Query

from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.lottery import RULES, LotteryType, LotteryUpdateResponse
from app.schemas.predict import LotteryOption, PredictRequest, PredictResponse
from app.schemas.prediction_tracking import (
    ModelEvaluationList,
    SavedPredictionList,
)
from app.schemas.purchase import (
    PurchaseCheckResponse,
    PurchaseListResponse,
    PurchaseRequest,
    PurchaseResponse,
    PurchaseStatus,
)
from app.services import (
    agent_service,
    chat_service,
    lottery_update_service,
    model_profile_service,
    predict_service,
    prediction_tracking_service,
    purchase_service,
)

router = APIRouter(prefix="/api")

@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """質問を受け取り、モデルの返答を返す"""
    return ChatResponse(answer=chat_service.ask(request.question))


@router.get("/lotteries", response_model=list[LotteryOption])
def lotteries():
    """画面の選択肢に出す宝くじの種類の一覧を返す"""
    return [LotteryOption(value=lottery, name=RULES[lottery].name) for lottery in LotteryType]


@router.post("/lottery-data/update", response_model=LotteryUpdateResponse)
def update_lottery_data():
    """公式サイトの最新結果を確認し、DBにない抽せん結果と賞金を追加する"""
    try:
        added_draws, added_prizes = lottery_update_service.update_latest_draws()
        if added_draws:
            prediction_tracking_service.evaluate_pending()
        return LotteryUpdateResponse(added_draws=added_draws, added_prizes=added_prizes)
    except lottery_update_service.LotteryDataConflictError as error:
        raise HTTPException(status_code=409, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except lottery_update_service.OfficialSiteError as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    """宝くじの種類と組数を受け取り、予想した番号と当せん確率を返す"""
    try:
        profile = model_profile_service.load_model_profile(request.lottery)
        result = predict_service.predict(
            request.lottery,
            request.count,
            profile.config,
            profile.model_version,
        )
        prediction_tracking_service.save_prediction(result)
        return result
    except predict_service.NoDrawDataError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.get("/predictions", response_model=SavedPredictionList)
def predictions(
    lottery: LotteryType | None = None,
    limit: int = Query(default=20, ge=1, le=200),
):
    """保存済み予想を新しい順に返す。"""
    return SavedPredictionList(
        predictions=prediction_tracking_service.list_predictions(lottery, limit)
    )


@router.get("/model-evaluations", response_model=ModelEvaluationList)
def model_evaluations(
    lottery: LotteryType | None = None,
    limit: int = Query(default=20, ge=1, le=200),
):
    """保存済みの偏りモデル評価を新しい順に返す。"""
    return ModelEvaluationList(
        evaluations=prediction_tracking_service.list_evaluations(lottery, limit)
    )


@router.post("/purchases", response_model=PurchaseResponse)
def purchase(request: PurchaseRequest):
    """購入した番号を記録する"""
    try:
        return purchase_service.save_purchase(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/purchases", response_model=PurchaseListResponse)
def purchases(
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    round_number: int | None = Query(default=None, ge=1),
    status: PurchaseStatus | None = None,
):
    """購入の一覧と、全体の収支を返す"""
    if not any((date_from, date_to, round_number, status)):
        return purchase_service.list_purchases()
    try:
        return purchase_service.list_purchases(
            date_from=date_from,
            date_to=date_to,
            round_number=round_number,
            status=status,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.post("/purchases/check", response_model=PurchaseCheckResponse)
def check_purchases():
    """結果がまだの購入を抽選結果と照らし合わせ、一覧と全体の収支を返す"""
    return purchase_service.check_results()


@router.post("/agent", response_model=AgentResponse)
def agent(request: AgentRequest):
    """AI エージェントに質問し、返答を返す"""
    return AgentResponse(answer=agent_service.ask(request.message, request.thread_id))
