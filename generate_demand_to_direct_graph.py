import csv
import json
import os
from collections import defaultdict


# Folder containing the graph node JSON files
GRAPH_FOLDER = "stops"

# CSV file containing passenger movements
CSV_FILE = "data.csv"


# Demand vector order:
# index 0 -> morning_1
# index 1 -> morning_2
# index 2 -> afternoon_1
# index 3 -> afternoon_2
# index 4 -> night_1
# index 5 -> night_2
SHIFTS = [
    "manha_1",
    "manha_2",
    "tarde_1",
    "tarde_2",
    "noite_1",
    "noite_2"
]


ZERO_VECTOR = [0, 0, 0, 0, 0, 0]


def add_vectors(first, second):
    """
    Adds two demand vectors.

    Example:

    [2,0,1,0,0,0]
    +
    [1,1,0,0,0,0]

    Result:

    [3,1,1,0,0,0]
    """

    return [
        first[i] + second[i]
        for i in range(6)
    ]



def load_csv_demand(csv_file):
    """
    Converts passenger CSV records into directed edge demand.

    The CSV represents movements:

        EMBARKING STOP  --->  ALIGHTING STOP


    Example CSV row:

    turno,embarque,desembarque
    manha_1,A,B


    Creates:

    (A,B) -> [1,0,0,0,0,0]


    Each CSV line represents one passenger.
    The lotacao field is intentionally ignored.
    """

    demand = defaultdict(
        lambda: ZERO_VECTOR.copy()
    )


    with open(
        csv_file,
        "r",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)


        for row in reader:

            origin = row["embarque"].strip()
            destination = row["desembarque"].strip()
            shift = row["turno"].strip()


            if shift not in SHIFTS:
                continue


            shift_index = SHIFTS.index(
                shift
            )


            # One CSV record = one passenger
            passenger = 1


            # Directed graph edge:
            #
            # origin -> destination
            #
            demand[
                (origin, destination)
            ][shift_index] += passenger


    return demand



def load_graph(folder):
    """
    Loads existing graph nodes.

    Each JSON file represents a graph node:

    {
        "label": "NODE NAME",
        "edges": []
    }

    The label is used as the node identifier.
    """

    graph = {}


    for filename in os.listdir(folder):

        if not filename.endswith(".json"):
            continue


        path = os.path.join(
            folder,
            filename
        )


        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:

            graph[filename] = json.load(file)


    return graph



def calculate_alightings(graph, demand):
    """
    Calculates incoming passenger flow.

    For every directed edge:

        A -> B

    the demand is added to node B.

    Therefore:

    alightings(B) =
        sum(all edges ending at B)
    """

    alightings = defaultdict(
        lambda: ZERO_VECTOR.copy()
    )


    for node in graph.values():

        origin = node["label"]


        for edge in node.get("edges", []):

            destination = edge["destination"]


            edge_flow = demand.get(
                (origin, destination),
                ZERO_VECTOR
            )


            alightings[destination] = add_vectors(
                alightings[destination],
                edge_flow
            )


    return alightings



def save_graph_json(path, node):
    """
    Saves JSON preserving the desired format.

    Arrays are written in one line:

    "boardings": [1,2,3,4,5,6]

    "demand": [1,2,3,4,5,6]
    """

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write("{\n")


        file.write(
            f'    "label": {json.dumps(node["label"], ensure_ascii=False)},\n'
        )

        file.write(
            f'    "boardings": {node["boardings"]},\n'
        )

        file.write(
            f'    "alightings": {node["alightings"]},\n'
        )


        file.write(
            '    "edges": [\n'
        )


        for index, edge in enumerate(node["edges"]):

            file.write(
                "        {\n"
            )


            file.write(
                f'            "destination": {json.dumps(edge["destination"], ensure_ascii=False)},\n'
            )

            file.write(
                f'            "distance": {edge["distance"]},\n'
            )

            file.write(
                f'            "estimated_travel_time": {edge["estimated_travel_time"]},\n'
            )

            file.write(
                f'            "demand": {edge["demand"]}\n'
            )


            file.write(
                "        }"
            )


            if index < len(node["edges"]) - 1:
                file.write(",")


            file.write("\n")


        file.write(
            "    ]\n"
        )

        file.write(
            "}\n"
        )



def update_graph(graph_folder, graph, demand):
    """
    Updates the directed graph.

    For each node:

    1. Updates every outgoing edge:
        edge.demand = passenger flow


    2. Calculates boardings:

        boardings(node) =
        sum(outgoing edges)


    3. Calculates alightings:

        alightings(node) =
        sum(incoming edges)
    """

    alightings = calculate_alightings(
        graph,
        demand
    )


    for filename, node in graph.items():

        origin = node["label"]


        boardings = ZERO_VECTOR.copy()


        for edge in node.get("edges", []):

            destination = edge["destination"]


            flow = demand.get(
                (origin, destination),
                ZERO_VECTOR.copy()
            )


            # Store passenger flow on directed edge
            edge["demand"] = flow


            # Accumulate outgoing passengers
            boardings = add_vectors(
                boardings,
                flow
            )


        node["boardings"] = boardings


        node["alightings"] = alightings.get(
            origin,
            ZERO_VECTOR.copy()
        )


        output = os.path.join(
            graph_folder,
            filename
        )


        save_graph_json(
            output,
            node
        )


        print(
            f"Updated: {filename}"
        )



if __name__ == "__main__":

    # Step 1:
    # Convert CSV passenger movements
    # into directed edge demand
    demand = load_csv_demand(
        CSV_FILE
    )


    # Step 2:
    # Load graph nodes
    graph = load_graph(
        GRAPH_FOLDER
    )


    # Step 3:
    # Inject demand into graph
    # and calculate node flows
    update_graph(
        GRAPH_FOLDER,
        graph,
        demand
    )


    print(
        "Directed graph conversion completed."
    )