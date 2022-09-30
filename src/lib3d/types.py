# Standard Library
import typing as t
from dataclasses import dataclass
from dataclasses import field

# Third Party Library
import bpy.types


@dataclass
class BpyContextSceneRenderImageConfig:
    color_mode: str = "RGBA"  # ('RGB', 'RGBA', ...)
    file_format: str = "PNG"  # ('PNG', 'OPEN_EXR', 'JPEG, ...)


@dataclass
class BpyContextSceneRenderConfig:
    # Blender internal engine for rendering
    # E.g. CYCLES, BLENDER_EEVEE, ...'
    engine: str = "BLENDER_EEVEE"
    image_settings: BpyContextSceneRenderImageConfig = BpyContextSceneRenderImageConfig()
    resolution_x: int = 600
    resolution_y: int = 600


@dataclass
class BpyContextSceneConfig:
    render: BpyContextSceneRenderConfig


@dataclass
class BpyContextConfig:
    scene: BpyContextSceneConfig


@dataclass
class BpyConfig:
    context: BpyContextConfig


@dataclass
class InputObjectConfig:
    obj_filepath: str  # "data/sphere.obj"
    obj_name: str  # "sphere"
    location: t.List[float]


@dataclass
class InputConfig:
    objects: t.List[InputObjectConfig]
    depth_image_path: str  # "data/depth.png"


@dataclass
class DebugConfig:
    output_dir: str
    mask_image_path: str
    blend_filepath: str


@dataclass
class ConfigModel:
    config: str  # default config filepath
    bpy: BpyConfig
    input: InputConfig
    debug: DebugConfig
    render_filepath: str  # "sample_output" -> sample_output.png
    output_filepath_obj: str  # ./sample_output.obj
    debug_mode: bool = True
    # debug: DebugConfig = DebugConfig()


@dataclass
class BlenderMainReturn:
    template_obj: bpy.types.Object
    mold_obj_base: bpy.types.Object
    mold_obj_sub: bpy.types.Object


@dataclass
class CameraConfig:
    location: t.Tuple[float, float, float]
    max_depth_distance: float


@dataclass
class SceneObjectsConfig:
    cameras: t.List[CameraConfig] = field(default_factory=list)


@dataclass
class DebugRenderRGBConfig:
    output_dir: str
    blend_filepath: str


@dataclass
class RenderRGBDConfig:
    bpy: BpyConfig
    scene_objects: SceneObjectsConfig

    shapenet_root_path: str
    output_root_dir: str
    metadata_filepath: str

    debug_mode: bool
    debug: t.Optional[DebugRenderRGBConfig] = None
