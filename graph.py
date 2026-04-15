import json
import networkx as nx
import matplotlib.pyplot as plt

# ==============
# GRAPH BUILDING
# ==============

with open("graph.json", "r", encoding="utf-8") as file:
    data = json.load(file)

G = nx.Graph()

for node in data["nodes"]:
    label = node.pop("label")
    G.add_node(label, **node)

for edge in data["edges"]:
    origin = edge.pop("origin")
    destination = edge.pop("destination")
    G.add_edge(origin, destination, **edge)

# ===================
# GRAPH VISUALIZATION
# ===================

node_positions = nx.spring_layout(G)

node_labels = {
    node: G.nodes[node].get("label", node)
    for node in G.nodes
}

edge_labels = {
    (origin, destination): (
        f"{attrs.get('distance', 0)} km\n"
        f"{attrs.get('estimated_travel_time', 0)} min"
    )
    for origin, destination, attrs in G.edges(data=True)
}

plt.figure(figsize=(8, 6))

nx.draw(
    G,
    node_positions,
    with_labels=False,
    node_size=2000,
    node_color="lightblue"
)

nx.draw_networkx_labels(
    G,
    node_positions,
    labels=node_labels
)

nx.draw_networkx_edge_labels(
    G,
    node_positions,
    edge_labels=edge_labels
)

plt.show()