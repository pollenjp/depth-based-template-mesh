# Standard Library
import math
import typing as t
from dataclasses import dataclass
from logging import NullHandler
from logging import getLogger
from pathlib import Path

# Third Party Library
import bpy
import mathutils
import numpy as np
import PIL
import PIL.Image
from mathutils import Euler

# Local Library
from .types import BlenderMainReturn
from .types import ConfigModel
from .utils import convert_to_location_vector
from .utils import subdivide_obj

logger = getLogger(__name__)
logger.addHandler(hdlr=NullHandler())


@dataclass
class RangeXY:
    xmin: float
    xmax: float
    ymin: float
    ymax: float


def depth_map2plane(
    depth_arr: np.ndarray, z_max: float = 1.0, grid_resolution: int = 135, background: int = 0
) -> bpy.types.Object:
    """

    3D座標では (x,y,z) の方向はそれぞれ +x が奥, +y が右, +z が上

    Args:
        depth_arr (np.ndarray):
            np.uint8
            upper left is (0, 0)

    Returns:
        bpy.types.Object:
            plane object は (0, 0, 0) と中心とした
            -1 <= x <= 1, -1 <= y <= 1 の範囲に生成される.
            depthに応じて +z 方向に浮き出させる.
    """
    (im_h, im_w) = depth_arr.shape[:2]

    plane_range = RangeXY(-1.0, 1.0, -1.0, 1.0)
    bpy.ops.mesh.primitive_plane_add(
        size=2.0, location=mathutils.Vector((0.0, 0.0, 0.0)), rotation=mathutils.Euler((0.0, 0.0, 0.0))
    )
    depth_obj = bpy.context.active_object

    if __debug__:
        logger.info(f"{depth_obj.name=}")
        logger.info(f"{depth_obj.data.name=}")
    # depth_obj.location = convert_to_location_vector((0.0, 0.0, 0.0))
    # depth_obj.rotation_euler = (0.0, 0.0, 0.0)

    # subdivide
    # depth_obj.data.primitive_grid_add(x_subdivisions=137, y_subdivisions=137)
    subdivide_obj(obj=depth_obj, num_cuts=grid_resolution)

    # mapping depth array to plane
    def get_depth_value_from_plane_coord(x: float, y: float) -> int:
        # im_x <- calculated from 3d y value
        # im_y <- calculated from 3d x value
        x_length = plane_range.xmax - plane_range.xmin
        im_y_rate: float = (x - plane_range.xmin) / x_length
        y_length = plane_range.ymax - plane_range.ymin
        im_x_rate: float = 1 - (y - plane_range.ymin) / y_length  # flip

        im_x = min(int(im_w * im_x_rate), im_w - 1)
        im_y = min(int(im_h * im_y_rate), im_h - 1)

        return int(depth_arr[im_y, im_x])

    def depth2z(depth: float) -> float:
        return z_max * (depth / 255.0)

    for v_idx, vertex in enumerate(depth_obj.data.vertices):
        (x, y, _z) = vertex.co
        d = get_depth_value_from_plane_coord(x, y)
        new_z = depth2z(d)

        # update vertex
        vertex.co = mathutils.Vector((x, y, new_z))

    return depth_obj


def load_obj(config: ConfigModel) -> BlenderMainReturn:
    # Set up rendering
    context = bpy.context
    scene = bpy.context.scene
    render = bpy.context.scene.render

    render.engine = config.bpy.context.scene.render.engine
    render.image_settings.color_mode = config.bpy.context.scene.render.image_settings.color_mode
    # render.image_settings.color_depth = args.color_depth  # ('8', '16')
    render.image_settings.file_format = config.bpy.context.scene.render.image_settings.file_format
    render.resolution_x = config.bpy.context.scene.render.resolution_x
    render.resolution_y = config.bpy.context.scene.render.resolution_y
    render.resolution_percentage = 100
    render.film_transparent = True

    scene.use_nodes = True
    scene.view_layers["View Layer"].use_pass_normal = True
    scene.view_layers["View Layer"].use_pass_diffuse_color = True
    scene.view_layers["View Layer"].use_pass_object_index = True

    nodes: bpy.types.Nodes = bpy.context.scene.node_tree.nodes
    # links: bpy.types.NodeLinks = bpy.context.scene.node_tree.links

    # Clear default nodes
    for n in nodes:
        nodes.remove(n)

    # Create input render layer node
    _ = nodes.new("CompositorNodeRLayers")
    # render_layers = nodes.new('CompositorNodeRLayers')

    # Delete default cube
    context.active_object.select_set(True)
    bpy.ops.object.delete()

    ##############
    # Load model #
    ##############

    def load_wavefront_obj(obj_path: Path, obj_name: str = None) -> bpy.types.Object:
        bpy.ops.object.select_all(action="DESELECT")  # deselect
        bpy.ops.import_scene.obj(filepath=str(obj_path))
        obj: bpy.types.Object = bpy.context.selected_objects[0]
        obj.name = obj_name
        # context.view_layer.objects.active = obj
        return obj

    for obj_info in config.input.objects:
        obj = load_wavefront_obj(obj_path=Path(obj_info.obj_filepath), obj_name=obj_info.obj_name)
        obj.location = convert_to_location_vector(obj_info.location)
        if __debug__:
            logger.info(f"{obj.name=}, {obj.location=}, {obj.data.name=}")

    template_obj = obj

    ########
    # Mold #
    ########

    #########################
    # depth to plane object #
    #########################

    filepath = Path(config.input.depth_image_path)
    im = np.array(PIL.Image.open(filepath))
    assert im.ndim == 2, f"{im.ndim=}"
    # TODO:
    depth_obj = depth_map2plane(depth_arr=255 - im)

    # less vertex
    decimate_modifier = depth_obj.modifiers.new(name="decimate", type="DECIMATE")
    decimate_modifier.ratio = 0.1
    bpy.context.view_layer.objects.active = depth_obj
    bpy.ops.object.modifier_apply(modifier=decimate_modifier.name)

    # rotate
    def rotate_obj(obj: bpy.types.Object, euler: Euler = Euler(map(math.radians, (0.0, 90.0, 180.0)), "XYZ")) -> None:
        """
        https://blender.stackexchange.com/questions/36647/python-low-level-apply-rotation-to-an-object
        """
        mat = obj.matrix_world * euler.to_matrix().to_4x4()
        obj.matrix_world = mat
        return obj

    euler: Euler = Euler(map(math.radians, (0.0, 90.0, 180.0)), "XYZ")
    depth_obj.rotation_euler = euler
    # depth_obj.matrix_world = euler.to_matrix().to_4x4() * depth_obj.matrix_world
    # bpy.context.view_layer.objects.active = depth_obj
    # depth_obj = rotate_obj(obj=depth_obj, euler=euler)

    obj = depth_obj
    center_vec = mathutils.Vector((-0.3, 0.0, 0.0))
    if __debug__:
        logger.info(f"{center_vec=}")
    obj.location = obj.location - center_vec
    del obj
    # end scope

    mold_obj_base = depth_obj

    bpy.ops.mesh.primitive_plane_add(size=2.0, location=depth_obj.location, rotation=depth_obj.rotation_euler)
    mold_obj_sub = bpy.context.active_object

    #########
    # Light #
    #########

    # # Make light just directional, disable shadows.
    # obj_light_name: str = "Light"
    # light1: bpy.types.Light = bpy.data.lights[obj_light_name]
    # light1.type = "SUN"
    # light1.use_shadow = False
    # # Possibly disable specular shading:
    # light1.specular_factor = 1.0
    # light1.energy = 10.0

    # # Add another light source so stuff facing away from light is not completely dark
    # bpy.ops.object.light_add(type="SUN")
    # light2: bpy.types.Light = bpy.data.lights["Sun"]
    # light2.use_shadow = False
    # light2.specular_factor = 1.0
    # light2.energy = 0.015
    # bpy.data.objects[light2.name].rotation_euler = bpy.data.objects[light1.name].rotation_euler
    # bpy.data.objects[light2.name].rotation_euler[0] += 180

    # # Place camera
    # cam = scene.objects["Camera"]
    # # cam.location = (0, 1, 0.6)
    # cam.location = (8.0, 7.0, 4.0)
    # cam.data.lens = 35
    # cam.data.sensor_width = 32

    # cam_constraint = cam.constraints.new(type="TRACK_TO")
    # cam_constraint.track_axis = "TRACK_NEGATIVE_Z"
    # cam_constraint.up_axis = "UP_Y"

    # cam_empty = bpy.data.objects.new("Empty", None)
    # cam_empty.location = (0, 0, 0)
    # cam.parent = cam_empty

    # scene.collection.objects.link(cam_empty)
    # context.view_layer.objects.active = cam_empty
    # cam_constraint.target = cam_empty

    # # Render
    # scene.render.filepath = config.render_filepath
    # bpy.ops.render.render(write_still=True)  # render still

    return BlenderMainReturn(template_obj=template_obj, mold_obj_base=mold_obj_base, mold_obj_sub=mold_obj_sub)
