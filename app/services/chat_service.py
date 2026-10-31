from langchain_openai import ChatOpenAI

from app.config import MODEL_NAME


def ask(question: str) -> str:
    """モデルに質問を送り、返答の文章を返す"""
    llm = ChatOpenAI(model=MODEL_NAME)
    response = llm.invoke(question)
    return response.content
