"""
$ python3 ./scripts/run.py --data_dir "data"
"""

# Standard Library
import argparse
import concurrent.futures
import os
import re
import subprocess
import typing as t
from dataclasses import dataclass
from logging import NullHandler
from logging import getLogger
from pathlib import Path

logger = getLogger(__name__)
logger.addHandler(NullHandler())


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("--data_dir", required=True, type=lambda x: Path(x).expanduser().absolute())
    parser.add_argument("--out_dir", required=True, type=lambda x: Path(x).expanduser().absolute())
    args = parser.parse_args()
    return args


def search_file_iter(dir: Path) -> t.Iterator[Path]:
    pattern = re.compile(
        # ignore files started from period (.)
        pattern=r"^(?!.*^\.)rendering_metadata.txt",
    )
    for _dirpath, _dirnames, _filenames in os.walk(dir):
        for _filename in _filenames:
            if pattern.match(string=_filename) is not None:
                yield Path(_dirpath) / _filename


@dataclass
class Cmd:
    cmd: t.List[str]
    category_id: str
    object_id: str
    env: t.Optional[t.Dict[str, str]] = None
    stdout: t.Optional[t.TextIO] = None
    stderr: t.Optional[t.TextIO] = None


def run_cmd(cmd: Cmd) -> None:
    subprocess.run(cmd.cmd, stdout=cmd.stdout, stderr=cmd.stderr, env=cmd.env)


def main() -> None:
    args = get_args()

    blender_cmd: Path = (Path.cwd() / ".local/blender/blender").resolve()
    assert blender_cmd.exists(), f"{blender_cmd} does not exists"

    py_file: Path = (Path(__file__).parent / "create_3dr2n2_with_depth.py").resolve()
    assert py_file.exists(), f"{py_file} does not exists"

    output_base_dir: Path = args.out_dir
    output_base_dir.mkdir(parents=True, exist_ok=True)

    default_config: Path = Path.cwd() / "config" / "create_3dr2n2_with_depth.yml"

    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
        future_to_fpath: t.Dict[concurrent.futures.Future[None], Cmd] = {}
        cmd: Cmd
        for i, filepath in enumerate(search_file_iter(args.data_dir)):
            # if i > 2:
            #     break
            logger.info(f"{i:>5}: {filepath}")
            if not filepath.exists():
                logger.error(f"{filepath} is not exists")
                continue

            output_filepath_obj: Path = (
                output_base_dir / filepath.parent.relative_to(args.data_dir) / f"{filepath.stem}.obj"
            )
            output_filepath_obj.parent.mkdir(parents=True, exist_ok=True)
            cmd = Cmd(
                cmd=[
                    str(blender_cmd),
                    "--background",
                    "--python",
                    f"{py_file}",
                    "--",
                    f"output_root_dir={output_base_dir}",
                    f"metadata_filepath={filepath}",
                    "debug_mode=False",
                ],
                category_id=filepath.parents[3].name,
                object_id=filepath.parents[2].name,
                env={"APP_CONFIG_PATH": f"{default_config}"},
                stdout=None,
                stderr=None,
            )
            future_to_fpath[executor.submit(run_cmd, cmd)] = cmd

        future: concurrent.futures.Future[None]
        for future in concurrent.futures.as_completed(future_to_fpath):
            cmd = future_to_fpath[future]
            try:
                future.result()
            except Exception as exc:
                logger.error(f"{exc}: Failed to process {cmd.category_id}/{cmd.object_id}")
            else:
                logger.info(f"Completed: {cmd.category_id}/{cmd.object_id}")


if __name__ == "__main__":
    # Standard Library
    import logging

    logging.basicConfig(
        format="[%(asctime)s][%(levelname)s][%(filename)s:%(lineno)d] - %(message)s",
        level=logging.INFO,
    )

    main()
