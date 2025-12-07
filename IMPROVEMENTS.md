# Package Improvement Recommendations

## 🔴 Critical Issues

### 1. **Public API Exposure**
**Issue**: Empty `__init__.py` files mean users must import from submodules.

**Fix**: Add proper exports to `src/speckle2graph/__init__.py`:
```python
from speckle2graph.parsers.traverseDAG import TraverseSpeckleDAG
from speckle2graph.graph_builders.simple_graph_builder import GraphBuilder
from speckle2graph.models.geometry import GeometryNode
from speckle2graph.models.logical import LogicalNode
from speckle2graph.neo4j_queries.basic_query import (
    write_logical_graph_to_neo4j,
    write_geometrical_graph_to_neo4j
)

__version__ = "0.0.1"
__all__ = [
    "TraverseSpeckleDAG",
    "GraphBuilder",
    "GeometryNode",
    "LogicalNode",
    "write_logical_graph_to_neo4j",
    "write_geometrical_graph_to_neo4j",
]
```

### 2. **Type Hints Missing**
**Issue**: Functions lack type annotations, making code harder to understand and maintain.

**Fix**: Add type hints throughout:
```python
from typing import Iterator, Optional, Dict, Set, Tuple
import numpy as np
import networkx as nx

def parse_obj(self, objects_to_skip: list[str] = []) -> Iterator[LogicalNode | GeometryNode]:
    ...
```

### 3. **Logging Instead of Print**
**Issue**: `print()` statements throughout code should use proper logging.

**Fix**: Replace all `print()` with logging:
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Success!")
logger.warning(f"Failed to build {head.name}")
```

### 4. **Hardcoded Test Credentials**
**Issue**: Tests contain real project IDs and require actual credentials.

**Fix**: Use fixtures, mocks, and environment variables with defaults.

## 🟡 Important Improvements

### 5. **Dependency Version Constraints**
**Issue**: `pyproject.toml` lacks version constraints.

**Fix**: Add version constraints:
```toml
dependencies = [
    "specklepy>=3.1.0",
    "numpy>=1.24.0",
    "scipy>=1.10.0",
    "trimesh>=4.0.0",
    "python-fcl>=0.7.0",
    "networkx>=3.0",
    "rtree>=1.0.0",
    "neo4j>=5.0.0",
    "tqdm>=4.65.0"
]
```

### 6. **Development Dependencies**
**Issue**: No dev dependencies for testing/linting.

**Fix**: Add to `pyproject.toml`:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "mypy>=1.0.0",
    "pytest-mock>=3.10.0",
]
```

### 7. **File Naming (PEP 8)**
**Issue**: `traverseDAG.py` should be `traverse_dag.py`.

**Fix**: Rename file and update imports.

### 8. **Documentation**
**Issue**: Missing docstrings and comprehensive README.

**Fix**: 
- Add docstrings to all public functions/classes
- Expand README with:
  - Installation instructions
  - Quick start example
  - API documentation
  - Contributing guidelines

### 9. **Error Handling**
**Issue**: Generic exception catching without proper handling.

**Fix**: Catch specific exceptions and provide meaningful error messages:
```python
except (ValueError, AttributeError) as e:
    logger.error(f"Failed to process {head.name}: {e}", exc_info=True)
    self.failed_objects[head.applicationId] = head
```

### 10. **Performance Optimization**
**Issue**: Creating new `CollisionManager` for each intersection pair check.

**Fix**: Reuse collision manager or batch operations:
```python
def _find_intersection_pairs(self) -> Set[Tuple[str, str]]:
    from trimesh.collision import CollisionManager
    collision_manager = CollisionManager()
    
    # Add all objects once
    for obj in self.geometrical_objects.values():
        collision_manager.add_object(name=obj.id, mesh=obj.geometry)
    
    # Then check collisions
    ...
```

## 🟢 Nice-to-Have Improvements

### 11. **Constants for Magic Strings**
**Issue**: Hardcoded strings like "CONTAINS", "CONNECTED_TO" scattered throughout.

**Fix**: Define constants:
```python
# In a constants.py file
EDGE_TYPE_CONTAINS = "CONTAINS"
EDGE_TYPE_CONNECTED_TO = "CONNECTED_TO"
```

### 12. **Configuration Management**
**Issue**: Configuration scattered across code.

**Fix**: Use a config class or dataclass for settings.

### 13. **Unit Tests**
**Issue**: Only integration tests exist.

**Fix**: Add unit tests for individual functions/classes with mocks.

### 14. **Type Checking**
**Issue**: No type checking setup.

**Fix**: Add `mypy` configuration and type stubs.

### 15. **Code Formatting**
**Issue**: Inconsistent formatting.

**Fix**: Add `black` and `ruff` for consistent formatting.

### 16. **CI/CD Pipeline**
**Issue**: No automated testing/checks.

**Fix**: Add GitHub Actions for:
- Running tests
- Type checking
- Linting
- Building package

### 17. **Example Scripts**
**Issue**: No usage examples.

**Fix**: Add `examples/` directory with sample scripts.

### 18. **Null Safety**
**Issue**: Missing null checks (e.g., `containedElementsIds` could be None).

**Fix**: Add proper null checks:
```python
if value.containedElementsIds is not None:
    for contained_element in value.containedElementsIds:
        ...
```

## 📋 Priority Order

1. **High Priority** (Do First):
   - Public API exposure (#1)
   - Type hints (#2)
   - Logging (#3)
   - Dependency versions (#5)
   - File naming (#7)

2. **Medium Priority**:
   - Documentation (#8)
   - Error handling (#9)
   - Performance (#10)
   - Dev dependencies (#6)

3. **Low Priority**:
   - Constants (#11)
   - Unit tests (#13)
   - CI/CD (#16)
   - Examples (#17)


