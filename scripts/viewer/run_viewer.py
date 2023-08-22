#!/usr/bin/env python
"""
Starts viewer in eval mode.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, fields
from pathlib import Path
from threading import Thread
from typing import Optional

import tyro
from rich.console import Console

from nerfstudio.configs.base_config import ViewerConfig
from nerfstudio.engine.trainer import TrainerConfig
from nerfstudio.pipelines.base_pipeline import Pipeline
from nerfstudio.utils import writer
from nerfstudio.utils.eval_utils import eval_setup
from nerfstudio.viewer.server.viewer_state import ViewerState

CONSOLE = Console(width=120)


@dataclass
class ViewerConfigWithoutNumRays(ViewerConfig):
    """Configuration for viewer instantiation"""

    num_rays_per_chunk: tyro.conf.Suppress[int] = -1

    def as_viewer_config(self):
        """Converts the instance to ViewerConfig"""
        return ViewerConfig(**{x.name: getattr(self, x.name) for x in fields(self)})


@dataclass
class RunViewer:
    """Load a checkpoint and start the viewer."""

    load_config: Path
    """Path to config YAML file."""
    ViewerState: ViewerState = None
    """视图渲染地址"""
    viewer: ViewerConfigWithoutNumRays = field(default_factory=ViewerConfigWithoutNumRays)
    """Viewer configuration"""
    websocket_port: Optional[int] = None
    """The websocket port to connect to. If None, find an available port."""
    progress_key: str = "nerf_studio:run_viewer"
    """点云导出进度，redis缓存键"""

    def main(self) -> None:
        """Main function."""
        config, pipeline, _, step = eval_setup(
            self.load_config,
            eval_num_rays_per_chunk=None,
            test_mode="test",
            progress_key=self.progress_key,
        )
        num_rays_per_chunk = config.viewer.num_rays_per_chunk
        assert self.viewer.num_rays_per_chunk == -1
        config.vis = "viewer"
        config.viewer = self.viewer.as_viewer_config()
        config.viewer.num_rays_per_chunk = num_rays_per_chunk
        if self.websocket_port is not None:
            config.viewer.websocket_port = self.websocket_port
        # 开启视图并进入阻塞
        _start_viewer(self, config, pipeline, step)

    def save_checkpoint(self, *args, **kwargs):
        """
        Mock method because we pass this instance to viewer_state.update_scene
        """


def _start_viewer(runviewer: RunViewer, config: TrainerConfig, pipeline: Pipeline, step: int):
    """Starts the viewer

    Args:
        config: Configuration of pipeline to load
        pipeline: Pipeline instance of which to load weights
        step: Step at which the pipeline was saved
    """
    base_dir = config.get_base_dir()
    viewer_log_path = base_dir / config.viewer.relative_log_filename
    # 初始化视图
    viewer_state = ViewerState(
        config.viewer,
        log_filename=viewer_log_path,
        datapath=pipeline.datamanager.get_datapath(),
        pipeline=pipeline,
    )
    runviewer.ViewerState = viewer_state
    banner_messages = [f"Viewer at: {viewer_state.viewer_url}"]
    # We don't need logging, but writer.GLOBAL_BUFFER needs to be populated
    config.logging.local_writer.enable = False
    writer.setup_local_writer(config.logging, max_iter=config.max_num_iterations, banner_messages=banner_messages)

    assert viewer_state and pipeline.datamanager.train_dataset
    viewer_state.init_scene(
        dataset=pipeline.datamanager.train_dataset,
        train_state="completed",
    )
    viewer_state.viser_server.set_training_state("completed")
    viewer_state.update_scene(step=step)
    # 后端websocket服务设置domain，启动线程阻塞
    # while True:
    #     time.sleep(0.01)


def entrypoint():
    """Entrypoint for use with pyproject scripts."""
    tyro.extras.set_accent_color("bright_yellow")
    tyro.cli(RunViewer).main()


if __name__ == "__main__":
    entrypoint()

# For sphinx docs
get_parser_fn = lambda: tyro.extras.get_parser(RunViewer)  # noqa
