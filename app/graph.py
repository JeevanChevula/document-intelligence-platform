import uuid
from functools import lru_cache
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agents.generation import generate_answer
from app.agents.retrieval import retrieve_relevant_chunks
from app.agents.router import route_query
from app.agents.validator import validate_answer


class GraphState(TypedDict):
    query: str
    user_id: str
    history: list[dict]
    # filenames the user owns, passed in by the caller so this module stays free
    # of any database dependency — the Router uses them to route on phrasing it
    # would otherwise misread
    document_names: list[str]
    route: str
    chunks: list[dict]
    answer: str
    is_valid: bool
    source: str


def router_node(state: GraphState) -> dict:
    return {"route": route_query(state["query"], state.get("document_names", []))}


def retrieval_node(state: GraphState) -> dict:
    chunks = retrieve_relevant_chunks(state["query"], uuid.UUID(state["user_id"]))
    return {"chunks": chunks}


def _determine_source(route: str, chunks: list[dict]) -> str:
    """Labels where an answer came from — provenance only.

    Deliberately independent of whether the Validator could confirm the answer.
    Those are two different questions, and collapsing them made the label lie:
    an advisory question ("what roles should I apply for based on my resume?")
    legitimately extrapolates beyond the documents, so it fails validation while
    still being genuinely document-grounded — and was being mislabelled
    "no_relevant_documents" despite clearly using the user's resume.
    Verification is carried separately, as `is_valid`.
    """
    if route == "general":
        return "general_knowledge"
    if not chunks:
        return "no_relevant_documents"
    return "documents"


def generation_node(state: GraphState) -> dict:
    chunks = state.get("chunks", [])
    answer = generate_answer(state["query"], chunks, state["route"], state.get("history", []))
    return {"answer": answer, "source": _determine_source(state["route"], chunks)}


def validation_node(state: GraphState) -> dict:
    is_valid, final_answer = validate_answer(state["answer"], state.get("chunks", []))
    return {"is_valid": is_valid, "answer": final_answer}


def _decide_route(state: GraphState) -> str:
    return state["route"]


@lru_cache
def get_graph():
    graph = StateGraph(GraphState)

    graph.add_node("router", router_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("generation", generation_node)
    graph.add_node("validation", validation_node)

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _decide_route, {"retrieval": "retrieval", "general": "generation"})
    graph.add_edge("retrieval", "generation")
    graph.add_edge("generation", "validation")
    graph.add_edge("validation", END)

    return graph.compile()


def run_agent_pipeline(
    query: str,
    user_id: uuid.UUID,
    history: list[dict] | None = None,
    document_names: list[str] | None = None,
) -> GraphState:
    initial_state: GraphState = {
        "query": query,
        "user_id": str(user_id),
        "history": history or [],
        "document_names": document_names or [],
        "route": "",
        "chunks": [],
        "answer": "",
        "is_valid": True,
        "source": "",
    }
    return get_graph().invoke(initial_state)
