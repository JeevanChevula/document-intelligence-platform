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
    route: str
    chunks: list[dict]
    answer: str
    is_valid: bool
    source: str


def router_node(state: GraphState) -> dict:
    return {"route": route_query(state["query"])}


def retrieval_node(state: GraphState) -> dict:
    chunks = retrieve_relevant_chunks(state["query"], uuid.UUID(state["user_id"]))
    return {"chunks": chunks}


def _determine_source(route: str, chunks: list[dict], is_valid: bool) -> str:
    """Labels where an answer actually came from.

    Retrieval no longer filters by similarity score (see search_chunks), so
    `chunks` being non-empty no longer reliably means the content was actually
    relevant. Instead, this leans on the Validator's judgment: if it couldn't
    confirm the answer is grounded in what was retrieved, that's treated the
    same as having found nothing useful — both are cases where the user
    shouldn't trust the answer as coming confidently from their documents.
    """
    if route == "general":
        return "general_knowledge"
    if not chunks or not is_valid:
        return "no_relevant_documents"
    return "documents"


def generation_node(state: GraphState) -> dict:
    chunks = state.get("chunks", [])
    answer = generate_answer(state["query"], chunks, state["route"], state.get("history", []))
    return {"answer": answer}


def validation_node(state: GraphState) -> dict:
    chunks = state.get("chunks", [])
    is_valid, final_answer = validate_answer(state["answer"], chunks)
    source = _determine_source(state["route"], chunks, is_valid)
    return {"is_valid": is_valid, "answer": final_answer, "source": source}


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


def run_agent_pipeline(query: str, user_id: uuid.UUID, history: list[dict] | None = None) -> GraphState:
    initial_state: GraphState = {
        "query": query,
        "user_id": str(user_id),
        "history": history or [],
        "route": "",
        "chunks": [],
        "answer": "",
        "is_valid": True,
        "source": "",
    }
    return get_graph().invoke(initial_state)
