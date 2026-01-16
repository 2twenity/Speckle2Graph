"""Base traverser class with common DAG traversal logic"""
from collections import deque
from typing import Generator, Iterable, Callable
from loguru import logger

from specklepy.objects.data_objects import DataObject
from specklepy.objects.models.collections.collection import Collection
from specklepy.objects.proxies import InstanceProxy 
from specklepy.objects.proxies import InstanceDefinitionProxy
from specklepy.objects.geometry import Mesh

from ..models.logical import LogicalNode 
from ..models.geometry import GeometryNode
from .property_extractors import PropertyExtractor
from ..utils.helpers import transform_faces
from ..utils.helpers import transform_vertices

import json
import numpy as np
import trimesh


class BaseTraverseDAG:
    """Base class for traversing DAG structures with vendor-specific property extraction"""
    
    def __init__(
        self, 
        speckle_root: DataObject, 
        property_extractor: PropertyExtractor,
        objects_to_skip: list[str] = [],
        logical_filter: Callable[[Collection, list[str]], bool] | None = None
    ) -> None:
        """
        Initialize the traverser
        
        Args:
            speckle_root: Root DataObject to traverse
            property_extractor: Strategy for extracting vendor-specific properties
            objects_to_skip: List of object IDs to skip during traversal
        """
        self.root = speckle_root
        self.property_extractor = property_extractor
        # Predicate to decide whether to yield a logical Collection node.
        # Signature: (collection, immediate_contained_ids) -> bool
        self.logical_filter = logical_filter or (lambda _col, _ids: True)
        self.instanced_objects: dict[str, LogicalNode | GeometryNode] = {}
        # Keep references to yielded logical nodes so we can update their
        # contained_elements_ids when geometries are discovered.
        self._yielded_logicals: dict[str, LogicalNode] = {}
        self.flattened_speckle_dag = self._traverse_dag(objects_to_skip=objects_to_skip)

    def __str__(self):
        return f"Traversed DAG with root name: {self.root.name}"

    def __iter__(self) -> Iterable[LogicalNode|GeometryNode]:
        return iter(self.flattened_speckle_dag)

    def _get_instance_definition_proxies(self) -> dict[str, list[InstanceProxy]]:
        """
        Get instance definition proxies. Override in subclasses for vendor-specific behavior.
        
        Returns:
            Dictionary mapping definition IDs to lists of InstanceProxy objects
        """
        instance_definition_proxies = getattr(self.root, "instanceDefinitionProxies", [])
        return {el.applicationId: el.objects for el in instance_definition_proxies}

    def _get_vendor_specific_instanced_objects_collection_name(self) -> str:
        """
        Get the name of the collection containing instanced objects.
        Must be overridden in subclasses for vendor-specific behavior.
        
        Returns:
            Collection name string
            
        Raises:
            NotImplementedError: If not overridden in subclass
        """
        raise NotImplementedError(
            "Subclasses must implement _get_instanced_objects_collection_name() "
            "to return the vendor-specific collection name for instanced objects"
        )

    def _traverse_dag(self, objects_to_skip: list[str]|None = None) -> Generator[LogicalNode | GeometryNode, None, None]:
        """
        Traverse the DAG and yield logical and geometrical nodes
            
        Args:
            objects_to_skip: speckle_id of collections that should not be traversed
        """

        if objects_to_skip == None:
            objects_to_skip = []

        self.failed_objects: dict[str, DataObject] = {}
        number_of_fails: int = 0
        items_yielded: int = 0

        instance_definition_proxies_map = self._get_instance_definition_proxies()
        logger.info("{} proxies were found", len(instance_definition_proxies_map))
        # print(f"{len(instance_definition_proxies_map)} proxies were found")

        stack: deque[tuple[Collection|DataObject|InstanceProxy, str|None]] = deque()
        stack.append((self.root, None))
    
        while len(stack) > 0:
            head, parent_id = stack.pop()

            # Check if the head is a Collection of reusable BIM elements
            # If yes, build an index with a key of applicationId
            instanced_objects_name = self._get_vendor_specific_instanced_objects_collection_name()
            if isinstance(head, Collection) and head.name == instanced_objects_name:
                self.instanced_objects = {}
                for element in head.elements:
                    self.instanced_objects[element.applicationId] = element
                logger.info("{} instances were found", len(self.instanced_objects))

            # If head is collection, iterate over it and add to stack
            elif isinstance(head, Collection) and head.id not in objects_to_skip:
                elements_ids_contained_in_logical_element = [el.id for el in head.elements]

                keep = self.logical_filter(head, elements_ids_contained_in_logical_element)
                
                for el in head.elements:
                    if keep:
                        stack.append((el, head.id))
                    else:
                        stack.append((el, parent_id))
                
                if keep:
                    logical_node = LogicalNode(
                        id=head.id,
                        name=head.name,
                        contained_elements_ids=elements_ids_contained_in_logical_element,
                        speckle_type=head.speckle_type
                    )
                    # Save reference so we can append discovered geometry ids later
                    self._yielded_logicals[head.id] = logical_node
                    items_yielded += 1
                    yield logical_node

            elif isinstance(head, list):
                for el in head:
                    stack.append(el)

            elif hasattr(head, "displayValue") and head.displayValue != []:
                object_display_value = head.displayValue

                geometries_for_trimesh: list[Mesh] = []
                transform_matrices: list[np.array] = []

                for obj in object_display_value:

                    # Address a case when the object is a proxy
                    if isinstance(obj, InstanceProxy):
                        definition_application_ids = instance_definition_proxies_map.get(obj.definitionId, [])
                        transform_matrix = np.array(obj.transform).reshape(4, 4)
                        transform_matrices.append(transform_matrix)
                        for Id in definition_application_ids:
                            speckle_mesh = self.instanced_objects[Id]  # Get referenced meshes
                            geometries_for_trimesh.append(speckle_mesh)

                    elif isinstance(obj, Mesh):
                        geometries_for_trimesh.append(obj)

                try:
                    if len(geometries_for_trimesh) == 0:
                        logger.warning("No geometries found for {}", head.name)
                        continue
                    
                    trimeshes = [
                        trimesh.Trimesh(
                            faces=transform_faces(mesh.faces),
                            vertices=transform_vertices(mesh.vertices)
                        ) for mesh in geometries_for_trimesh
                    ]

                    if len(trimeshes) > 1:
                        result_mesh: trimesh.Trimesh = trimesh.util.concatenate(a=trimeshes[0], b=trimeshes[1:])
                    elif len(trimeshes) == 1:
                        result_mesh: trimesh.Trimesh = trimeshes[0]

                    if len(transform_matrices) > 0:
                        mesh_to_transform = result_mesh.copy()
                        result_mesh = mesh_to_transform.apply_transform(transform_matrices[0])

                    bounding_box: np.ndarray = result_mesh.bounding_box.bounds  # Shape: (2, 3) - min and max corners
                    single_array_bounding_box: tuple[np.float64] = (*bounding_box[0], *bounding_box[1])

                    # Use property extractor to get vendor-specific type classifier
                    type_classifier: str = self.property_extractor.extract_type_classifier(head)

                    geometry_node = GeometryNode(
                        name=head.name,
                        id=head.id,
                        category=type_classifier,  # Store vendor-specific type classifier
                        speckle_type=head.speckle_type,
                        geometry=result_mesh,
                        centroid=result_mesh.centroid,
                        raw_vertices=result_mesh.vertices,
                        raw_faces=result_mesh.faces,
                        bounding_box=single_array_bounding_box,
                        properties=json.dumps(head.properties)
                    )
                    # If this geometry has a parent logical node (after forwarding),
                    # attach its id to that logical's contained list so the graph
                    # builder will create the logical->geometry relationship.
                    if parent_id is not None and parent_id in self._yielded_logicals:
                        parent_logical = self._yielded_logicals[parent_id]
                        if parent_logical.contained_elements_ids is None:
                            parent_logical.contained_elements_ids = [geometry_node.id]
                        elif geometry_node.id not in parent_logical.contained_elements_ids:
                            parent_logical.contained_elements_ids.append(geometry_node.id)

                    items_yielded += 1
                    yield geometry_node

                except Exception as e:
                    number_of_fails += 1
                    logger.error(
                        "Failed to build {} (failure #{}): {}",
                        head.name,
                        number_of_fails,
                        str(e)
                    )
                    failed_id = getattr(head, 'applicationId', None) or head.id
                    self.failed_objects[failed_id] = head
        
        logger.info(
            "Parsing complete: {} objects yielded, {} failed",
            items_yielded,
            number_of_fails
        )
        
    def get_failed_objects(self) -> dict[str, DataObject]:
        """Get dictionary of objects that failed during traversal"""
        return self.failed_objects