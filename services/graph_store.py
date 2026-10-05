import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import networkx as nx


logger = logging.getLogger(__name__)

DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data"
DEFAULT_GRAPH_PATH = DATA_DIRECTORY / "graph.json"


class GraphStoreError(RuntimeError):
    """Raised when the graph cannot be persisted or restored."""


def initialize_graph() -> nx.MultiDiGraph:
    """Create an empty directed graph that supports parallel relationships."""

    return nx.MultiDiGraph()


def load_graph(path: Path = DEFAULT_GRAPH_PATH) -> nx.MultiDiGraph:
    """Load a graph from disk, or create an empty graph if none exists."""

    if not path.exists():
        logger.info("No saved graph found at %s; initializing an empty graph.", path)
        return initialize_graph()

    try:
        with path.open("r", encoding="utf-8") as graph_file:
            graph_data: dict[str, Any] = json.load(graph_file)

        loaded_graph = nx.node_link_graph(
            graph_data,
            directed=True,
            multigraph=True,
            edges="edges",
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, nx.NetworkXError) as exc:
        logger.exception("Failed to load graph from %s.", path)
        raise GraphStoreError(f"Failed to load graph from {path}.") from exc

    logger.info(
        "Loaded graph from %s with %d nodes and %d edges.",
        path,
        loaded_graph.number_of_nodes(),
        loaded_graph.number_of_edges(),
    )
    return cast(nx.MultiDiGraph, loaded_graph)


graph = load_graph()


def add_node(
    entity: str,
    attributes: Mapping[str, Any] | None = None,
) -> None:
    """Add an entity node to the in-memory graph."""

    normalized_entity = entity.strip()
    if not normalized_entity:
        raise ValueError("Entity names must not be empty.")

    graph.add_node(normalized_entity, **dict(attributes or {}))


def add_edge(
    source_entity: str,
    relationship_type: str,
    target_entity: str,
    attributes: Mapping[str, Any] | None = None,
) -> None:
    """Add a directed entity-relationship-entity triple to the graph."""

    normalized_source = source_entity.strip()
    normalized_relationship = relationship_type.strip()
    normalized_target = target_entity.strip()

    if not normalized_source or not normalized_target:
        raise ValueError("Source and target entity names must not be empty.")
    if not normalized_relationship:
        raise ValueError("Relationship types must not be empty.")

    edge_attributes = dict(attributes or {})
    edge_attributes["relationship_type"] = normalized_relationship
    graph.add_edge(normalized_source, normalized_target, **edge_attributes)


def save_graph(path: Path = DEFAULT_GRAPH_PATH) -> None:
    """Persist the in-memory graph as node-link JSON using an atomic replace."""

    temporary_path = path.with_suffix(f"{path.suffix}.tmp")

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        graph_data = nx.node_link_data(graph, edges="edges")

        with temporary_path.open("w", encoding="utf-8") as graph_file:
            json.dump(graph_data, graph_file, ensure_ascii=False, indent=2)

        temporary_path.replace(path)
    except (OSError, TypeError, nx.NetworkXError) as exc:
        logger.exception("Failed to save graph to %s.", path)
        raise GraphStoreError(f"Failed to save graph to {path}.") from exc

    logger.info(
        "Saved graph to %s with %d nodes and %d edges.",
        path,
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )
