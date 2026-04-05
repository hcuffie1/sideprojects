from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.nodes.intent_node import intent_node
from agent.nodes.retrieval_node import retrieval_node
from agent.nodes.constraint_check_node import constraint_check_node
from agent.nodes.ranking_node import ranking_node
from agent.nodes.groundedness_node import groundedness_node
from agent.nodes.response_node import response_node


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("intent", intent_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("constraint_check", constraint_check_node)
    graph.add_node("ranking", ranking_node)
    graph.add_node("groundedness", groundedness_node)
    graph.add_node("response", response_node)

    graph.set_entry_point("intent")
    graph.add_edge("intent", "retrieval")
    graph.add_edge("retrieval", "constraint_check")
    graph.add_edge("constraint_check", "ranking")
    graph.add_edge("ranking", "groundedness")
    graph.add_edge("groundedness", "response")
    graph.add_edge("response", END)

    return graph.compile()


agent = build_graph()
