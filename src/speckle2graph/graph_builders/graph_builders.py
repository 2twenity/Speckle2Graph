import networkx as nx
from rtree import index
from tqdm import tqdm
from trimesh import Trimesh
from loguru import logger

from ..traversers.traverse_revit_dag import TraverseRevitDAG
from ..traversers.traverse_ifc_dag import TraverseIFCDAG
from ..models.geometry import GeometryNode
from ..models.logical import LogicalNode
from ..utils.helpers import flatten_dictionary

import json
import numpy as np
from typing import Optional, Iterable

class DataGraphBuilder:
    def __init__(self, traversed_speckle_object: Iterable[LogicalNode|GeometryNode]) -> None:
        self._traversed_speckle_object = traversed_speckle_object
        self._logical_objects = {}
        self._geometrical_objects = {}
        self.logical_graph = nx.DiGraph()
        self.geometrical_graph = nx.DiGraph()

        p = index.Property()
        p.dimension = 3
        self._spatial_index = index.Index(properties=p)
    
    def _separate_logical_and_geometrical_objects(self) -> None:
        for speckle_object in self._traversed_speckle_object:
            if isinstance(speckle_object, LogicalNode):
                self._logical_objects[speckle_object.id] = speckle_object
            elif isinstance(speckle_object, GeometryNode):
                self._geometrical_objects[speckle_object.id] = speckle_object

    def _build_logical_graph(self, edge_type="CONTAINS") -> None:
        
        if self._logical_objects == {}:
            logger.info("Calling a method to separate logical and geometrical elements")
            self._separate_logical_and_geometrical_objects()

        for key, value in self._logical_objects.items():
            self.logical_graph.add_node(key, name=value.name, id=value.id, speckle_type=value.speckle_type, logical_write_status=True)

            for contained_element in value.contained_elements_ids:
                self.logical_graph.add_node(contained_element, id=contained_element, logical_write_status=False)
                self.logical_graph.add_edge(key, contained_element, name=edge_type, logical_write_status=False)

        for edge in self.logical_graph.edges(data=True):
            first_node = self.logical_graph.nodes[edge[0]]
            second_node = self.logical_graph.nodes[edge[1]]
            
            if first_node['logical_write_status'] and second_node['logical_write_status']:
                edge[2]['logical_write_status'] = True

        logger.info(
            "Logical graph built: {} nodes, {} edges",
            self.logical_graph.number_of_nodes(),
            self.logical_graph.number_of_edges()
        )
        # print(f"Logical graph built: {self.logical_graph.number_of_nodes()} nodes, {self.logical_graph.number_of_edges()} edges")

    def _build_geometries_index(self) -> None:
        for i, obj in enumerate(self._geometrical_objects.values()):
            self._spatial_index.insert(i, obj.bounding_box, obj=obj.id)

    def _find_intersection_pairs(self, precision: float = 0.05) -> tuple[str, str]:
        from trimesh.collision import CollisionManager
        intersection_pairs = set()

        self._build_geometries_index()

        for element in tqdm(self._geometrical_objects.values(), desc="Finding intersecting geometries"):
            for intersection in self._spatial_index.intersection(element.bounding_box, objects=True):
                if element.id != intersection.object:

                    collisionManager = CollisionManager()

                    collisionManager.add_object(
                        name = element.id, 
                        mesh = element.geometry)

                    collisionManager.add_object(
                        name = intersection.object, 
                        mesh = self._geometrical_objects[intersection.object].geometry)

                    collision_result: tuple[bool, Optional[set[tuple[str, str]]]] = collisionManager.in_collision_internal(return_names=True)
                    boolean_collision_result = collision_result[0]
                    
                    distance_result: tuple[float, tuple[str, str]] = collisionManager.min_distance_internal(return_names=True)
                    distance: float = distance_result[0]
                    distance_check_pair_of_meshes_ids: tuple[str, str] = distance_result[1]

                    if not boolean_collision_result and distance < precision and distance > 0:
                        intersection_pairs.add(distance_check_pair_of_meshes_ids)

                    if boolean_collision_result:
                        set_of_intersecting_pairs: set[tuple[str, str]] = collision_result[1]
                        intersection_pair: tuple = next(iter(set_of_intersecting_pairs))
                        intersection_pairs.add(intersection_pair)
                        
        return intersection_pairs

    def _build_geometrical_graph(self, edge_type="CONNECTED_TO", precision: float = 0.05) -> None:
        if len(self._geometrical_objects) == 0:
            self._separate_logical_and_geometrical_objects()

        for obj in self._geometrical_objects.values():
            try:
                node_properties = json.loads(obj.properties)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse properties for {}: {}", obj.name, e)
                # print(f"Failed to parse properties for {obj.name}: {e}")
                continue
            
            properties = flatten_dictionary(node_properties)
    
            self.geometrical_graph.add_node(
                obj.id,
                name = obj.name,
                category = obj.category,
                speckle_type = obj.speckle_type,
                properties = properties,
                centroid = obj.centroid,
                raw_faces = str(obj.raw_faces),
                raw_vertices = str(obj.raw_vertices)
            )
            
        intersection_pairs = self._find_intersection_pairs(precision=precision)

        for pair in intersection_pairs:
            first_centroid = self._geometrical_objects[pair[0]].centroid
            second_centroid = self._geometrical_objects[pair[1]].centroid
            centroid_based_distance = np.linalg.norm(second_centroid - first_centroid)
    
            self.geometrical_graph.add_edge(pair[0], pair[1], name = edge_type, distance = centroid_based_distance)

        logger.info(
            "Geometrical graph built: {} nodes, {} edges",
            self.geometrical_graph.number_of_nodes(),
            self.geometrical_graph.number_of_edges()
        )
        print(f"Geometrical graph built: {self.geometrical_graph.number_of_nodes()} nodes, {self.geometrical_graph.number_of_edges()} edges")

    def build_graph(self, build_geometrical_graph: bool = True, build_logical_graph: bool = True) -> None:
        if build_geometrical_graph:
            self._build_geometrical_graph()
        if build_logical_graph:
            self._build_logical_graph()

    def get_geometries(self) -> list[GeometryNode]:
        return [i for i in self._geometrical_objects.values()]