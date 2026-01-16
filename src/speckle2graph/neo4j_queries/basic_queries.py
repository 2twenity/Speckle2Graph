from typing import Optional, TYPE_CHECKING
from ..graph_builders.graph_builders import DataGraphBuilder
from .label_makers import Neo4jRevitLabelAssigner
from .label_makers import Neo4jIfcLabelAssigner
from .label_makers import Neo4jLabelAssigner
from tqdm import tqdm

if TYPE_CHECKING:
    from neo4j import Driver

class Neo4jClientDriverWrapper:
    def __init__(
        self, 
        driver: "Driver", 
        graph_builder_object: DataGraphBuilder, 
        label_assigner: Optional[Neo4jLabelAssigner] = None
        ) -> None:
        """
        Initialize Neo4j client wrapper with dependency injection.
        
        Args:
            driver: Neo4j database driver instance
            graph_builder_object: Graph builder containing the graph to write
            label_assigner: Label assigner instance. If None, defaults to Neo4jRevitLabelAssigner.
        """
        self.neo4j_client_driver = driver
        self.graph_builder_object = graph_builder_object
        self.label_assigner = label_assigner if label_assigner is not None else Neo4jRevitLabelAssigner()

    def _write_mapping_geometry_to_logic_to_neo4j(self, batch_size: int = 100) -> None:
        """Template query to write geometrical to logical mapping edges to Neo4j database"""

        mapping_edges_for_neo4j = [
            {
                "geometrical_id": edge[0],
                "logical_id": edge[1]
            } 
                for edge in self.graph_builder_object.logical_graph.edges(data=True) if edge[2]['logical_write_status'] == False
        ]

        for i in tqdm(range(0, len(mapping_edges_for_neo4j), batch_size), desc="Writing Geometrical to Logical Mapping Batches to Neo4j"):
            batch = mapping_edges_for_neo4j[i:i + batch_size]
            self.neo4j_client_driver.execute_query("""
                UNWIND $batch as edge_data
                MATCH (g {id: edge_data.geometrical_id}),(l {id: edge_data.logical_id})
                MERGE (l)-[:IS_INSTANCE_OF]->(g);         
                """,
                batch = batch
            )

    def _write_logical_graph_to_neo4j(self, batch_size: int = 100) -> None:
        """Template query to write logical nodes and edges to Neo4j database"""
        
        self.neo4j_client_driver.execute_query("""CREATE CONSTRAINT speckle_id_unique IF NOT EXISTS FOR (n:Collection) REQUIRE (n.id) IS UNIQUE""")

        logical_nodes_for_neo4j = [
            {
                "id": node[0],
                "name": node[1]['name'],
                "speckle_type": node[1]['speckle_type']
            } 
                for node in self.graph_builder_object.logical_graph.nodes(data=True) if node[1]["logical_write_status"] 
        ]

        logical_edges_for_neo4j = [
            {
                "source_id": edge[0],
                "target_id": edge[1],
                "connect_name": edge[2]["name"]
            } 
                for edge in self.graph_builder_object.logical_graph.edges(data=True) if edge[2]["logical_write_status"] 
        ]    

        for i in tqdm(range(0, len(logical_nodes_for_neo4j), batch_size), desc="Writing Logical Nodes Batches to Neo4j"):
            batch = logical_nodes_for_neo4j[i:i + batch_size]
            self.neo4j_client_driver.execute_query("""
                UNWIND $batch as node_data
                MERGE (n:Collection {id: node_data.id, name: node_data.name, speckle_type: node_data.speckle_type} );         
                """,
                batch = batch
            )

        for i in tqdm(range(0, len(logical_edges_for_neo4j), batch_size), desc="Writing Logical Edges Batches to Neo4j"):
            batch = logical_edges_for_neo4j[i:i + batch_size]
            self.neo4j_client_driver.execute_query("""
                UNWIND $batch as edge_data
                MATCH (n1 {id: edge_data.source_id}),(n2 {id: edge_data.target_id})
                MERGE (n1)-[:CONTAINS {name: edge_data.connect_name}]->(n2);         
                """,
                batch = batch
            )
        
    def _write_geometrical_graph_to_neo4j(self, batch_size: int = 100) -> None:
        """Template query to write geometrical nodes and edges to Neo4j database"""

        grouped_geometrical_nodes_for_batching = {}
        for node in self.graph_builder_object.geometrical_graph.nodes(data=True):

            node_for_writing = {
                "id": node[0],
                "name": node[1]['name'],
                "centroid": node[1]['centroid'],
                "category": node[1]['category'],
                "speckle_type": node[1]['speckle_type'],
                "properties": node[1]['properties']
            }

            grouped_geometrical_nodes_for_batching.setdefault(node_for_writing['category'], []).append(node_for_writing)

        geometrical_edges_for_neo4j = [
            {
                "source_id": edge[0],
                "target_id": edge[1],
                "connect_name": edge[2]["name"],
                "distance": edge[2]["distance"]
            } 
                for edge in self.graph_builder_object.geometrical_graph.edges(data=True)
        ]

        for key, value in grouped_geometrical_nodes_for_batching.items():
            for i in tqdm(range(0, len(value), batch_size), desc=f"Writing {key} Nodes Batches to Neo4j"):
                batch = value[i:i + batch_size]
                first_string_part = "UNWIND $batch as node_data MERGE (n:"
                second_string_part = f"{self.label_assigner.assign_label(category=key)}"
                third_string_part = " {id: node_data.id, name: node_data.name, centroid: node_data.centroid, category: node_data.category} ) SET n += node_data.properties;"
                query_string = first_string_part + second_string_part + third_string_part
                self.neo4j_client_driver.execute_query(query_string, batch = batch)

        for i in tqdm(range(0, len(geometrical_edges_for_neo4j), batch_size), desc="Writing Geometrical Edges Batches to Neo4j"):
            batch = geometrical_edges_for_neo4j[i:i + batch_size]
            self.neo4j_client_driver.execute_query("""
                UNWIND $batch as edge_data
                MATCH (n1 {id: edge_data.source_id}),(n2 {id: edge_data.target_id})
                MERGE (n1)-[:CONNECTED_TO {name: edge_data.connect_name, distance: edge_data.distance}]->(n2);         
                """,
                batch = batch
            )

    def write_graph(
        self, 
        write_logical: bool = True, 
        write_geometrical: bool = True, 
        batch_size: int = 100
        ) -> None:
        """
        Function to write a graph to Neo4j

        Args:
            write_logical: if True, the hierarchy graph will be written
            write_geometrical: if True, the geometrical adjacency graph will be written
            batch_size: defines a size of a batch
        """
        if write_logical == False:
            self._write_geometrical_graph_to_neo4j(batch_size=batch_size)
        elif write_geometrical == False:
            self._write_logical_graph_to_neo4j(batch_size=batch_size)
        else:
            self._write_logical_graph_to_neo4j(batch_size=batch_size)
            self._write_geometrical_graph_to_neo4j(batch_size=batch_size)
            self._write_mapping_geometry_to_logic_to_neo4j(batch_size=batch_size)