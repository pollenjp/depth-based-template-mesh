# Standard Library
import math
import random
import typing as t
from logging import NullHandler
from logging import getLogger
from math import pi

# Third Party Library
import bmesh  # type: ignore # no stub file
import bpy
import mathutils
import numpy as np
from sympy.geometry.line import Line3D
from sympy.geometry.plane import Plane
from sympy.geometry.point import Point3D

logger = getLogger(__name__)
logger.addHandler(NullHandler())


def convert_deg2rad(deg: float) -> float:
    return deg * pi / 180.0


def get_randomint_point(
    x_range: t.Tuple[int, int] = (0, 100),
    y_range: t.Tuple[int, int] = (0, 100),
    z_range: t.Tuple[int, int] = (0, 100),
) -> mathutils.Vector:
    return mathutils.Vector((random.randint(0, 100), random.randint(0, 100), random.randint(0, 100)))


def sampling_on_plane(p1: Point3D, normal_vector: Point3D) -> t.Tuple[float, float, float]:
    plane: Plane = t.cast(Plane, Plane(p1, normal_vector))  # type: ignore # error: Call to untyped function
    n: Point3D = t.cast(Point3D, plane.normal_vector)
    # sample_x = Point3D(np.random.randint(3, 50, size=3))
    sample_x: Point3D = Point3D(np.random.rand(3))  # type: ignore # error: Call to untyped function
    # TODO: tkitou
    line: Line3D = Line3D(sample_x, sample_x + 2 * Point3D(n))  # type: ignore # error: Call to untyped function
    intersection: Point3D = t.cast(Point3D, plane.intersection(line)[0])  # type: ignore # error: Call to untyped function
    return (float(intersection.x), float(intersection.y), float(intersection.z))


_LocationLike = t.TypeVar("_LocationLike", t.List[int], t.Tuple[float, float, float], mathutils.Vector)


def convert_to_location_vector(location: _LocationLike) -> mathutils.Vector:
    if len(location) != 3:
        raise ValueError(f"{location=} not supported format!")
    if isinstance(location, mathutils.Vector):
        return location
    return mathutils.Vector(location)


def create_mesh_object(
    name: str,
    vertices: t.List[mathutils.Vector],
    edges: t.Optional[t.List[t.Tuple[int, int]]] = None,
    faces: t.Optional[t.List[t.Sequence[int]]] = None,
    scene_collection_name: str = "Collection",
) -> None:
    if edges is None:
        edges = []
    if faces is None:
        faces = []
    new_mesh = bpy.data.meshes.new(f"{name}_mesh")
    for i in range(0, len(vertices) - 1):
        for j in range(i + 1, len(vertices)):
            diff: mathutils.Vector = vertices[i] - vertices[j]
            if diff.length < 0.001:
                err_msg: str = f"index {i=}, {j=} are same"
                logger.error(err_msg)
                # raise ValueError(err_msg)
                return
    new_mesh.from_pydata(vertices, edges, faces)
    # new_mesh.update()

    new_object = bpy.data.objects.new(f"{name}_object", new_mesh)

    name2collection: t.Dict[str, bpy.types.Collection] = {c.name: c for c in bpy.data.collections}

    if scene_collection_name not in name2collection:
        name2collection[scene_collection_name] = bpy.data.collections.new(f"{scene_collection_name}")
        bpy.context.scene.collection.children.link(name2collection[scene_collection_name])

    collection: bpy.types.Collection = name2collection[scene_collection_name]
    collection.objects.link(new_object)

    return


def debug_line(name: str, p0: mathutils.Vector, p1: mathutils.Vector) -> None:
    create_mesh_object(name=name, vertices=[p0, p1], edges=[(0, 1)])
    return


def whether_intersection_is_inside_polygon(
    vertices: t.List[mathutils.Vector],
    intersection: mathutils.Vector,
    normal: mathutils.Vector,
) -> bool:
    angle_sum: float = 0
    for v1_idx, v2_idx in zip(range(0, len(vertices)), range(1, len(vertices) + 1)):
        v2_idx %= len(vertices)
        v1, v2 = vertices[v1_idx], vertices[v2_idx]
        tmp1: mathutils.Vector = v1 - intersection
        tmp2: mathutils.Vector = v2 - intersection
        v12_vec: mathutils.Vector = v2 - v1
        angle_degree: float = tmp1.angle(tmp2) * 180 / math.pi
        if abs(tmp1.length + tmp2.length - v12_vec.length) < 0.01:
            # detect whether the intersection is on the edge
            return True
        cross: mathutils.Vector = tmp1.cross(tmp2)
        if cross.dot(normal) < 0:
            angle_degree *= -1
        angle_sum += angle_degree

    angle_sum /= 360
    return abs(angle_sum) >= 0.1


def subdivide_obj(obj: bpy.types.Object, num_cuts: int = 1) -> None:
    """object を細分化

    Args:
        obj (bpy.types.Object): _description_
        num_cuts (int, optional): _description_. Defaults to 1.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=num_cuts, use_grid_fill=True)
    bm.to_mesh(obj.data)
    obj.update_from_editmode()
