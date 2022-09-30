# Standard Library
import logging
import math
import os
import sys
import typing as t
from logging import NullHandler
from logging import getLogger
from pathlib import Path

# Third Party Library
import bpy
import mathutils
from omegaconf import OmegaConf

logger = getLogger(__name__)
logger.addHandler(NullHandler())

sys.path.insert(0, f"{Path(__file__).parent / 'src'}")

if t.TYPE_CHECKING:
    # Local Library
    from .src.lib3d.types import BpyConfig
    from .src.lib3d.types import RenderRGBDConfig
    from .src.lib3d.types import SceneObjectsConfig
else:
    # First Party Library
    from lib3d.types import BpyConfig
    from lib3d.types import RenderRGBDConfig
    from lib3d.types import SceneObjectsConfig


_PathLike = t.TypeVar("_PathLike", Path, str)
_LocationLike = t.TypeVar("_LocationLike", t.List[int], t.Tuple[float, float, float], mathutils.Vector)


def parse_config() -> RenderRGBDConfig:

    args: t.List[str] = sys.argv[1:]
    custom_args: t.List[str] = []
    for i, arg in enumerate(args):
        if arg == "--":
            custom_args = args[i + 1 :]
            break

    if (path := os.environ.get("APP_CONFIG_PATH")) is None:
        raise ValueError("APP_CONFIG_PATH is not set!")

    config_filepath: Path = Path(path).expanduser()

    config: RenderRGBDConfig = t.cast(
        RenderRGBDConfig,
        OmegaConf.merge(
            OmegaConf.structured(RenderRGBDConfig),
            OmegaConf.load(config_filepath),
            OmegaConf.from_dotlist(custom_args),
        ),
    )

    return config


def convert_to_location_vector(location: _LocationLike) -> mathutils.Vector:
    if len(location) != 3:
        raise ValueError(f"{location=} not supported format!")
    if isinstance(location, mathutils.Vector):
        return location
    return mathutils.Vector(location)


class ShapeNetRender:
    def __init__(self, config_bpy: BpyConfig, config_scene_objects: SceneObjectsConfig):
        self.config_bpy = config_bpy
        self.config_scene_objects = config_scene_objects

        # Set up rendering
        self.context = bpy.context
        self.scene = bpy.context.scene
        bpy_cntx_scene_render = bpy.context.scene.render

        bpy_cntx_scene_render.engine = config_bpy.context.scene.render.engine
        bpy_cntx_scene_render.image_settings.color_mode = config_bpy.context.scene.render.image_settings.color_mode
        # render.image_settings.color_depth = args.color_depth  # ('8', '16')
        bpy_cntx_scene_render.image_settings.file_format = config_bpy.context.scene.render.image_settings.file_format
        bpy_cntx_scene_render.resolution_x = config_bpy.context.scene.render.resolution_x
        bpy_cntx_scene_render.resolution_y = config_bpy.context.scene.render.resolution_y
        bpy_cntx_scene_render.resolution_percentage = 100
        bpy_cntx_scene_render.film_transparent = True

        self.scene.use_nodes = True
        self.scene.view_layers["View Layer"].use_pass_normal = True
        self.scene.view_layers["View Layer"].use_pass_diffuse_color = True
        self.scene.view_layers["View Layer"].use_pass_object_index = True

        bpy.context.scene.world.color = (1, 1, 1)
        bpy.context.scene.render.resolution_percentage = 100

        self.nodes: bpy.types.Nodes = bpy.context.scene.node_tree.nodes

        # Clear default nodes
        for n in self.nodes:
            self.nodes.remove(n)

        # Create input render layer node
        self.render_layers = self.nodes.new("CompositorNodeRLayers")

        # depth
        # Create depth output nodes
        self.depth_file_output = self.nodes.new(type="CompositorNodeOutputFile")
        self.depth_file_output.label = "Depth Output"
        self.depth_file_output.base_path = ""
        self.depth_file_output.file_slots[0].use_node_format = True
        self.depth_file_output.format.file_format = "PNG"
        self.depth_file_output.format.color_depth = "8"  # 8 bit per channel
        self.depth_file_output.format.color_mode = "BW"

        # Remap as other types can not represent the full range of depth.
        depth_map = self.nodes.new(type="CompositorNodeMapValue")
        # Size is chosen kind of arbitrarily, try out until you're satisfied with resulting depth map.
        depth_map.offset = [-0.7]
        depth_map.size = [1.4]
        depth_map.use_min = True
        depth_map.min = [0]

        links = bpy.context.scene.node_tree.links
        links.new(self.render_layers.outputs["Depth"], depth_map.inputs[0])
        links.new(depth_map.outputs[0], self.depth_file_output.inputs[0])

        # Delete default cube
        self.context.active_object.select_set(True)
        bpy.ops.object.delete()

        self.init_lighting()

        # set camera
        self.init_camera()

    def init_lighting(self) -> None:
        #########
        # Light #
        #########

        # Make light just directional, disable shadows.
        obj_light_name: str = "Light1"
        light1_data: bpy.types.Light = bpy.data.lights.new(obj_light_name, type="POINT")
        light1_data.type = "POINT"
        light1_data.type = "SUN"
        light1_data.use_shadow = False
        # Possibly disable specular shading:
        # light1_data.specular_factor = 1.0
        light1_data.energy = 0.7
        self.light1_object = bpy.data.objects.new(name=obj_light_name, object_data=light1_data)

        # Add another light source so stuff facing away from light is not completely dark
        obj_light2_name: str = "Light2"
        light2_data = bpy.data.lights.new(obj_light2_name, type="POINT")
        light2_data.use_shadow = False
        # light2_data.specular_factor = 1.0
        light2_data.energy = 0.7
        self.light2_object = bpy.data.objects.new(name=obj_light2_name, object_data=light2_data)

        self.light1_object.rotation_euler = (math.radians(45), 0, math.radians(90))
        self.light2_object.rotation_euler = (-math.radians(45), 0, math.radians(90))
        self.light1_object.location = convert_to_location_vector((0, -2, 2))
        self.light2_object.location = convert_to_location_vector((0, 2, 2))

        bpy.context.scene.collection.objects.link(self.light1_object)
        bpy.context.scene.collection.objects.link(self.light2_object)

    def init_camera(self) -> None:
        # Place camera
        camera_idx: int = 0
        self.cam = self.scene.objects["Camera"]
        self.cam.location = convert_to_location_vector(self.config_scene_objects.cameras[camera_idx].location)
        self.cam.rotation_mode = "ZXY"
        self.cam.rotation_euler = (0, math.radians(90), math.radians(90))

        # self.cam.data.sensor_width = 32

        self.cam_rotation_axis = bpy.data.objects.new("RotCenter", None)
        self.cam_rotation_axis.location = (0, 0, 0)
        self.cam_rotation_axis.rotation_euler = (0, 0, 0)
        self.scene.collection.objects.link(self.cam_rotation_axis)
        self.cam.parent = self.cam_rotation_axis

        self.context.view_layer.objects.active = self.cam_rotation_axis

    def set_viewport(self, azimuth: float, elevation: float, yaw: float, distance_ratio: float, fov: float) -> None:
        """
        <https://github.com/chrischoy/3D-R2N2/blob/13a30e257cb2158c3bf5c2370d791073517ad22e/lib/blender_renderer.py#L132-L140>
        """

        self.cam.data.lens_unit = "FOV"
        self.cam.data.lens = fov

        self.cam_rotation_axis.rotation_euler = (0, 0, 0)

        # camera and light position
        cam_location: mathutils.Vector = convert_to_location_vector(
            (distance_ratio * self.config_scene_objects.cameras[0].max_depth_distance, 0, 0)
        )
        self.cam.location = cam_location
        self.light1_object.location = mathutils.Vector(
            (distance_ratio * (2 + self.config_scene_objects.cameras[0].max_depth_distance), 0, 0)
        )

        # camera axis rotation
        self.cam_rotation_axis.rotation_euler = (
            math.radians(-yaw),
            math.radians(-elevation),
            math.radians(-azimuth),
        )

    def load_object(self, object_filepath: _PathLike, object_name: str = "Model") -> bpy.types.Object:
        model_filepath: Path = Path(object_filepath)
        if model_filepath.suffix == ".obj":
            obj = self.load_wavefront_obj(obj_path=str(model_filepath), obj_name=object_name)
            obj.location = convert_to_location_vector(mathutils.Vector((0, 0, 0)))
            logger.info(f"{obj.name=}, {obj.location=}, {obj.data.name=}")
            return obj
        else:
            raise ValueError(f"{model_filepath=} not supported format!")

    def render(self, filepath: _PathLike) -> None:
        """save to f"{filepath}.<ext>". (<ext> is the file format)

        Args:
            filepath (_PathLike): [description]
        """
        self.scene.render.filepath = str(filepath)

        self.depth_file_output.file_slots[0].path = f"{filepath}_depth"

        bpy.ops.render.render(write_still=True)  # render still

    @staticmethod
    def load_wavefront_obj(obj_path: _PathLike, obj_name: t.Optional[str] = None) -> bpy.types.Object:
        bpy.ops.object.select_all(action="DESELECT")  # deselect
        bpy.ops.import_scene.obj(filepath=str(obj_path))
        obj: bpy.types.Object = bpy.context.selected_objects[0]
        obj.name = obj_name
        # context.view_layer.objects.active = obj
        return obj


def blender_main(config: RenderRGBDConfig, debug_mode: bool = False) -> None:

    # load metadata file
    metadata_filepath: Path = Path(
        # "ShapeNetP2M/04530566/ffffe224db39febe288b05b36358465d/rendering/rendering_metadata.txt"
        config.metadata_filepath
    ).expanduser()
    class_id: str = metadata_filepath.parents[2].name
    model_id: str = metadata_filepath.parents[1].name
    # /media/pollenjp/DATAHDD8TB/share/share01/dataset/ShapeNet/
    # ShapeNetCore.v1/04554684/fcc0bdba1a95be2546cde67a6a1ea328/model.obj
    shapenet_v1_root_path: Path = Path(config.shapenet_root_path).expanduser()
    model_path: Path = shapenet_v1_root_path / class_id / model_id / "model.obj"
    output_dir_path: Path = Path(config.output_root_dir).expanduser() / class_id / model_id / "rendering"

    renderer = ShapeNetRender(config.bpy, config.scene_objects)
    _ = renderer.load_object(model_path, object_name="TargetModel")
    with open(metadata_filepath, mode="rt") as f:
        i: int
        line: str
        for i, line in enumerate(f):
            line = line.rstrip()
            if not line:
                continue
            metadata: t.List[float] = list(map(float, line.split(" ")))

            renderer.set_viewport(*metadata)
            output_filepath: Path = output_dir_path / f"{i:02d}"
            output_filepath.parent.mkdir(parents=True, exist_ok=True)
            renderer.render(filepath=output_filepath)

    # For debugging the workflow
    if debug_mode is True and config.debug is not None:
        bpy.ops.wm.save_as_mainfile(filepath=f"{Path(config.debug.blend_filepath).expanduser()}")


def main() -> None:
    logging.basicConfig(
        format="[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] - %(message)s",
        level=logging.WARNING,
    )
    logger.setLevel(logging.INFO)

    config = parse_config()

    logger.info(f"{OmegaConf.to_yaml(config)=}")

    blender_main(config, debug_mode=config.debug_mode)


if __name__ == "__main__":
    main()
