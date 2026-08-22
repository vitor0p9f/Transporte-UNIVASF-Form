import json
import sys
from pathlib import Path


def format_stops(input_dir: str):
    input_path = Path(input_dir)
    nodes = []

    for file_path in sorted(input_path.glob("*.json")):
        with file_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        edges = data.get("edges", data.get("edges", []))

        edges.sort(
            key=lambda edge: int(edge["destination"])
        )

        node = {
            "label": data["label"],
            "boardings": data.get("boardings", [0] * 6),
            "alightings": data.get("alightings", [0] * 6),
            "edges": edges,
        }

        nodes.append(node)

    with open("graph.json", "w", encoding="utf-8") as file:
        file.write("{\n")
        file.write('  "nodes": [\n')

        for index, node in enumerate(nodes):
            file.write("    {\n")
            file.write(f'      "label": {json.dumps(node["label"])},\n')
            file.write(
                f'      "boardings": {json.dumps(node["boardings"])},\n'
            )
            file.write(
                f'      "alightings": {json.dumps(node["alightings"])},\n'
            )
            file.write('      "edges": [\n')

            edges = node["edges"]

            for edge_index, edge in enumerate(edges):
                line = "        " + json.dumps(
                    edge,
                    separators=(", ", ": ")
                )

                if edge_index < len(edges) - 1:
                    line += ","

                file.write(line + "\n")

            file.write("      ]\n")
            file.write("    }")

            if index < len(nodes) - 1:
                file.write(",")

            file.write("\n")

        file.write("  ]\n")
        file.write("}\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python format.py ./stops")
        sys.exit(1)

    format_stops(sys.argv[1])
