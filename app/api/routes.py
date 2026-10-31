from fastapi import APIRouter, HTTPException

from app.schemas.agent import AgentRequest, AgentResponse
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.lottery import RULES, LotteryType, LotteryUpdateResponse
from app.schemas.predict import LotteryOption, PredictRequest, PredictResponse
from app.schemas.purchase import (
    PurchaseCheckResponse,
    PurchaseListResponse,
    PurchaseRequest,
    PurchaseResponse,
)
from app.services import (
    agent_service,
    chat_service,
    lottery_update_service,
    predict_service,
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
        return predict_service.predict(request.lottery, request.count)
    except predict_service.NoDrawDataError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.post("/purchases", response_model=PurchaseResponse)
def purchase(request: PurchaseRequest):
    """購入した番号を記録する"""
    try:
        return purchase_service.save_purchase(request)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))


@router.get("/purchases", response_model=PurchaseListResponse)
def purchases():
    """購入の一覧と、全体の収支を返す"""
    return purchase_service.list_purchases()


@router.post("/purchases/check", response_model=PurchaseCheckResponse)
def check_purchases():
    """結果がまだの購入を抽選結果と照らし合わせ、一覧と全体の収支を返す"""
    return purchase_service.check_results()


@router.post("/agent", response_model=AgentResponse)
def agent(request: AgentRequest):
    """AI エージェントに質問し、返答を返す"""
    return AgentResponse(answer=agent_service.ask(request.message, request.thread_id))
