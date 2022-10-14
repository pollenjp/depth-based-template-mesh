# Standard Library
import logging
import sys
import typing as t
from logging import NullHandler
from logging import getLogger
from pathlib import Path

# Third Party Library
import bpy
import cv2
import mathutils
import nptyping as npt
import numpy as np
import PIL
import PIL.Image
from omegaconf import OmegaConf

# First Party Library
from lib3d import utils
from lib3d.load_obj import load_obj
from lib3d.types import BlenderMainReturn
from lib3d.types import ConfigModel

logger = getLogger(__name__)
logger.addHandler(NullHandler())


def get_args() -> ConfigModel:

    args: t.List[str] = sys.argv[1:]
    custom_args: t.List[str] = []
    for i, arg in enumerate(args):
        if arg == "--":
            custom_args = args[i + 1 :]
            break

    conf = OmegaConf.from_dotlist(custom_args)

    config: ConfigModel = t.cast(
        ConfigModel,
        OmegaConf.merge(
            OmegaConf.structured(ConfigModel),
            OmegaConf.load(conf.config),
            conf,
        ),
    )

    return config


def get_vertices_max_length(
    obj: bpy.types.Object,
    origin: mathutils.Vector = mathutils.Vector((0.0, 0.0, 0.0)),
) -> float:
    max_length: float = 0.0
    for mesh_vertex in obj.data.vertices:
        v_global: mathutils.Vector = obj.matrix_world @ mesh_vertex.co
        max_length = max(max_length, (v_global - origin).length)
    return max_length


def move_mesh_vertices(
    obj: bpy.types.Object,
    length: float,
    origin: mathutils.Vector = mathutils.Vector((0.0, 0.0, 0.0)),
) -> None:
    """メッシュの頂点を原点からlengthだけ離れた位置に移動する"""

    for mesh_vertex in obj.data.vertices:
        v_global: mathutils.Vector = obj.matrix_world @ mesh_vertex.co
        vec = v_global - origin
        unit_vec = vec / vec.length
        global_target_location = unit_vec * length
        mesh_vertex.co = obj.matrix_world.inverted() @ global_target_location


def create_mask(
    im: npt.NDArray[npt.Shape["*, ..."], npt.Int],
    background: int,
) -> npt.NDArray[npt.Shape["*, ..."], npt.Int]:
    """0,1のマスクを作成する

    Args:
        im (np.ndarray): _description_
        background (int): _description_

    Returns:
        np.ndarray: _description_
    """

    new_im = im.copy()

    new_im[im == background] = 0
    new_im[im != background] = 1

    size: int = 5
    kernel = np.ones((size, size), np.uint8)
    new_im = cv2.dilate(new_im, kernel, iterations=1)

    return new_im


def get_bounding_box_yz(obj3d: bpy.types.Object) -> t.Tuple[float, float, float, float]:
    y_max = -float("inf")
    y_min = +float("inf")
    z_max = -float("inf")
    z_min = +float("inf")
    for vertex in obj3d.data.vertices:
        vertex_coords = obj3d.matrix_world @ vertex.co
        y_max = max(y_max, vertex_coords.y)
        y_min = min(y_min, vertex_coords.y)
        z_max = max(z_max, vertex_coords.z)
        z_min = min(z_min, vertex_coords.z)
    return (y_min, z_min, y_max, z_max)


def move_mesh_vertices_with_mask(
    template_obj: bpy.types.Object,
    mold_obj: bpy.types.Object,
    mask_array: npt.NDArray[npt.Shape["*, *"], npt.Int],
    # upper left, upper right, lower left, lower right
    y_min: float,
    z_min: float,
    y_max: float,
    z_max: float,
    debug: bool = False,
) -> None:
    im_height, im_width = mask_array.shape[:2]

    for t_v_idx, t_v in enumerate(template_obj.data.vertices):
        t_v_global: mathutils.Vector = template_obj.matrix_world @ t_v.co

        best_intersection: mathutils.Vector = mathutils.Vector((0.0, 0.0, 0.0))

        # for polygon_idx, polygon in enumerate(mold_obj.data.polygons):
        for polygon in mold_obj.data.polygons:
            m_v_idx = polygon.vertices[0]
            # only rotation matrix
            extract_rotation_matrix = mathutils.Matrix(
                [
                    [1.0, 1.0, 1.0, 0.0],
                    [1.0, 1.0, 1.0, 0.0],
                    [1.0, 1.0, 1.0, 0.0],
                    [0.0, 0.0, 0.0, 1.0],
                ]
            )
            rotation_matrix = mold_obj.matrix_world * extract_rotation_matrix
            polygon_normal_global = rotation_matrix @ polygon.normal

            intersection: t.Optional[mathutils.Vector] = mathutils.geometry.intersect_line_plane(
                mathutils.Vector((0.0, 0.0, 0.0)),  # 原点からのベクトル
                t_v_global,
                mold_obj.matrix_world @ mold_obj.data.vertices[m_v_idx].co,
                polygon_normal_global,
            )
            if intersection is None:
                continue

            # filter with mask
            # TODO: create and use class method
            if (
                (intersection.y < y_min)
                or (intersection.y > y_max)
                or (intersection.z < z_min)
                or (intersection.z > z_max)
            ):
                continue
            w: int = int(im_width * (1 - (intersection.y - y_min) / (y_max - y_min)))
            h: int = int(im_height * (1 - (intersection.z - z_min) / (z_max - z_min)))
            assert 0 <= w < im_width and 0 <= h < im_height
            if mask_array[h, w] == 0:  # skip, if background
                continue

            # 逆向きを向いていたらスキップ
            # 中心から見て同じ方向にあるかどうか
            if t_v_global.dot(intersection) < 0:
                continue

            # TODO: check inside polygon or not
            # https://qiita.com/Mikoshi/items/9bc6215347c00fd849b3
            # if inside break forloop
            vertices: t.List[mathutils.Vector] = [
                mold_obj.matrix_world @ mold_obj.data.vertices[vertex_idx].co for vertex_idx in polygon.vertices
            ]
            if utils.whether_intersection_is_inside_polygon(
                vertices=vertices, intersection=intersection, normal=polygon.normal
            ):
                if intersection.length > best_intersection.length:
                    best_intersection = intersection

        # 条件に適合する交点がなかったらスキップ
        if best_intersection.length > 0.0:
            t_v.co = template_obj.matrix_world.inverted() @ best_intersection


def main() -> None:
    # Standard Library
    import pprint

    logging.basicConfig(
        format="[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] - %(message)s",
        level=logging.WARNING,
    )

    logger.info(f"\n{pprint.pformat(sys.path)}")

    config: ConfigModel = get_args()
    logger.info(f"{OmegaConf.to_yaml(config)=}")

    blender_main_val: BlenderMainReturn = load_obj(config)
    logger.info(f"{blender_main_val=}")

    # init template_obj's vertices

    # # get max length
    # max_length: float = max(
    #     get_vertices_max_length(obj=blender_main_val.mold_obj_base),
    #     get_vertices_max_length(obj=blender_main_val.mold_obj_sub),
    # )

    # # move vertices to the location
    # move_mesh_vertices(obj=blender_main_val.template_obj, length=max_length)

    # create mask from depth image and the mold
    # y-z 平面をベース
    # 1: foreground
    # 0: background
    # TODO: クラス化して内部か外部かを判定するコードにしてしまったほうが良い. (画像と座標の向きが一致している必要があるため.)
    mask_image: npt.NDArray[npt.Shape["*, *"], npt.Int] = create_mask(
        np.array(PIL.Image.open(Path(config.input.depth_image_path))),
        background=255,
    )

    if config.debug_mode:
        filepath: Path = Path(config.debug.mask_image_path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(filepath), mask_image * 255)

    mask_image = mask_image[:, ::-1]  # horizontal flip
    (y_min, z_min, y_max, z_max) = get_bounding_box_yz(blender_main_val.mold_obj_base)

    # calculate template and mold intersection and move vertices with a mask filter
    move_mesh_vertices_with_mask(
        template_obj=blender_main_val.template_obj,
        mold_obj=blender_main_val.mold_obj_base,
        mask_array=mask_image,
        y_min=y_min,
        z_min=z_min,
        y_max=y_max,
        z_max=z_max,
    )
    move_mesh_vertices_with_mask(
        template_obj=blender_main_val.template_obj,
        mold_obj=blender_main_val.mold_obj_sub,
        mask_array=mask_image,
        y_min=y_min,
        z_min=z_min,
        y_max=y_max,
        z_max=z_max,
    )

    # move_vertices_main(template_obj=blender_main_val.template_obj, mold_objs=blender_main_val.mold_objs, config=config)

    if config.debug_mode:  # For debugging the workflow
        logger.info("create files")
        bpy.ops.wm.save_mainfile(filepath=f"{Path(config.debug.blend_filepath).expanduser()}")
        bpy.ops.file.pack_all()

    # remove others
    bpy.ops.object.select_all(action="SELECT")
    blender_main_val.template_obj.select_set(False)
    bpy.ops.object.delete()

    # save as obj file

    bpy.context.view_layer.objects.active = blender_main_val.template_obj
    bpy.ops.export_scene.obj(filepath=config.output_filepath_obj)


if __name__ == "__main__":
    main()
