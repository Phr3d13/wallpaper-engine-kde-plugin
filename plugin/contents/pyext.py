#!/bin/python3

import asyncio
import websockets
import json
import base64
import math
import os
import platform
import shutil
import subprocess

from pathlib import Path

from typing import Callable,Any,Optional

# Audio capture: reads PCM from parec (PipeWire/PulseAudio monitor), computes
# a 64-bin FFT magnitude spectrum mirrored to stereo 128-bin array [L|R],
# stores the result in _audio_data so get_audio() can return it synchronously.
try:
    import numpy as _np
    _NUMPY_OK = True
except ImportError:
    _NUMPY_OK = False

_audio_data: list = [0.0] * 128
_run_max: float = 1.0
_audio_source_config: str = ''
_audio_restart_requested: bool = False

async def _find_monitor_source() -> str:
    """Return the best PulseAudio/PipeWire monitor source name.
    If the user has configured a specific source and it still exists, use it.
    Otherwise prefers the default source if it is a monitor, then any IDLE/RUNNING
    monitor, then any monitor at all. Falls back to '' (parec default)."""
    try:
        list_proc = await asyncio.create_subprocess_exec(
            'pactl', 'list', 'short', 'sources',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        list_out, _ = await list_proc.communicate()
        source_lines = list_out.decode().splitlines()
    except Exception:
        source_lines = []

    if _audio_source_config:
        available = {line.split()[1] for line in source_lines if len(line.split()) >= 2}
        if _audio_source_config in available:
            return _audio_source_config
        # configured source not found — fall through to auto-detect

    try:
        # Check default source first — if it's already a monitor, use it
        def_proc = await asyncio.create_subprocess_exec(
            'pactl', 'get-default-source',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        def_out, _ = await def_proc.communicate()
        default = def_out.decode().strip()
        if '.monitor' in default:
            return default

        # Otherwise scan sources, preferring non-SUSPENDED ones
        active = ''
        fallback = ''
        for line in source_lines:
            parts = line.split()
            if len(parts) < 2 or '.monitor' not in parts[1]:
                continue
            state = parts[4] if len(parts) >= 5 else ''
            if state in ('IDLE', 'RUNNING'):
                if not active:
                    active = parts[1]
            elif not fallback:
                fallback = parts[1]
        return active or fallback
    except Exception:
        pass
    return ''  # empty → parec uses the default source

async def _audio_capture_loop() -> None:
    """Continuously capture audio via parec and update _audio_data.

    Uses try/finally to guarantee the parec subprocess is always killed on
    every exit path: normal EOF, unhandled exception, or task cancellation
    (CancelledError).  This prevents orphaned parec processes.
    """
    global _audio_data, _run_max, _audio_restart_requested
    RATE  = 44100
    CHUNK = 1024
    BINS  = 64
    DECAY = 0.995
    bytes_per_frame = CHUNK * 4

    while True:
        _audio_restart_requested = False
        _was_restart = False
        proc = None
        try:
            source = await _find_monitor_source()
            if not source:
                # No monitor source available yet — PipeWire may still be
                # initializing at boot. Don't fall back to the default source
                # (usually the microphone input). Wait and retry.
                await asyncio.sleep(2)
                continue
            cmd = [
                'parec',
                '--format=float32le',
                f'--rate={RATE}',
                '--channels=1',
                '--latency-msec=30',
                '--stream-name=WEListener',
                '--device', source,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            buf = b''
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        proc.stdout.read(bytes_per_frame), timeout=2.0
                    )
                except asyncio.TimeoutError:
                    # parec produced no data (e.g. source is suspended at boot).
                    # Check restart flag so set_audio_source() is never blocked.
                    if _audio_restart_requested:
                        _was_restart = True
                        break
                    continue
                if not chunk:
                    break
                if _audio_restart_requested:
                    _was_restart = True
                    break
                buf += chunk
                while len(buf) >= bytes_per_frame:
                    frame, buf = buf[:bytes_per_frame], buf[bytes_per_frame:]
                    samples = _np.frombuffer(frame, dtype=_np.float32)
                    windowed = samples * _np.hanning(CHUNK)
                    mag = _np.abs(_np.fft.rfft(windowed, n=CHUNK))[:BINS].astype(float)
                    frame_max = float(_np.max(mag)) if mag.size else 0.0
                    _run_max = max(_run_max * DECAY, frame_max, 1e-6)
                    # Silence gate: if raw peak is below absolute floor, treat as silence.
                    # This prevents background noise from being normalised up to ~1.0
                    # when _run_max has decayed to near zero.
                    SILENCE_FLOOR = 0.01  # absolute FFT magnitude threshold
                    if frame_max < SILENCE_FLOOR:
                        _audio_data = [0.0] * 128
                    else:
                        scaled = (mag / _run_max).tolist()
                        _audio_data = scaled + scaled
        except asyncio.CancelledError:
            raise  # re-raise; finally block below handles cleanup
        except Exception:
            pass
        finally:
            # Always kill parec — runs on normal exit, exceptions, AND cancellation
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except OSError:
                    pass
        if not _was_restart:
            await asyncio.sleep(2)

# import functools;



class Main:
    def __init__(self):
        self.config_dir: Path = self.__config_dir()
        self.config_wallpaper_dir: Path = self.config_dir / 'wallpaper'

        self.config_wallpaper_dir.mkdir(parents=True, exist_ok=True)

    def __config_dir(self) -> Path:
        config_name: str = "wekde"
        xdg_config_home: Optional[str] = os.getenv("XDG_CONFIG_HOME")
        if xdg_config_home:
            return Path(xdg_config_home) / config_name
        return Path.home() / ".config" / config_name
    def __wallpaper_config_file(self, id: str) -> Path:
        return self.config_wallpaper_dir / (id + '.json')

    def read_wallpaper_config(self, id: str) -> dict:
        cfg_file: Path = self.__wallpaper_config_file(id)
        if not cfg_file.exists():
            return dict()

        with open(cfg_file, "r") as f:
            return json.load(f)

    def write_wallpaper_config(self, id: str, changed: dict) -> None:
        cfg: dict = self.read_wallpaper_config(id)
        cfg.update(changed)
        cfg_file: Path = self.__wallpaper_config_file(id)

        with open(cfg_file, "w+") as f:
            json.dump(cfg, f)

    def reset_wallpaper_config(self, id: str) -> None:
        cfg_file: Path = self.__wallpaper_config_file(id)
        cfg_file.unlink()

    def delete_wallpaper_config(self, id: str) -> None:
        cfg_file: Path = self.__wallpaper_config_file(id)
        if cfg_file.exists():
            cfg_file.unlink()

class Jsonrpc:
    def __init__(self):
        self.method_map = dict()

    def add_method(self, func: Callable) -> Callable:
        self.method_map[func.__name__] = func
        return func

    def add_class_method(self, obj: Any, func: Callable) -> None:
        def wrapper(*args):
            func(obj, *args)
        self.method_map[func.__name__] = wrapper

    def handle(self, msg) -> str:
        j: dict = {}
        error = None
        try:
            j = json.loads(msg)
        except Exception as e:
            error = repr(e)
            return json.dumps({"id": -1, "error": error})

        result = {"id": j.get("id")}
        method = j.get("method")
        if method in self.method_map:
            func = self.method_map[method]
            params = j.get("params") or []
            try:
                result["result"] = func(*params)
            except Exception as e:
                error = repr(e)
        else:
            error = "jsonrpc no such func"
        if error:
            result["error"] = error
        return json.dumps(result)

M = Main()
jrpc = Jsonrpc()


@jrpc.add_method
def version() -> str:
    return platform.python_version()


@jrpc.add_method
def readfile(path: str) -> str:
    with open(path, "rb") as f:
        data: bytes = f.read()
        return base64.b64encode(data).decode("ascii")


@jrpc.add_method
def get_dir_size(path: str, depth: int) -> int:
    glob_strs: list[str] = (
        ["**/*"]
        if depth <= 0
        else ["/".join(["*" for _ in range(i + 1)]) for i in range(depth)]
    )
    root_directory: Path = Path(path)
    return sum(
        [
            sum(f.stat().st_size for f in root_directory.glob(s) if f.is_file())
            for s in glob_strs
        ]
    )


@jrpc.add_method
def get_folder_list(path: str, _opt: dict = {}) -> Optional[dict]:
    def gen_item(f: Path) -> dict:
        stat: os.stat_result = f.stat()
        return {"name": f.name, "mtime": math.floor(stat.st_mtime)}

    opt: dict = get_folder_list.default_opt.copy()
    opt.update(_opt)
    opt_only_dir = opt["only_dir"]

    def path_filter(p: Path) -> bool:
        return p.is_dir() if opt_only_dir else True

    folder: Optional[Path] = next(
        filter(lambda p: p.is_dir(), [Path(p) for p in [path, *opt["fallbacks"]]]), None
    )
    if folder is None:
        return None
    return {
        "folder": str(folder),
        "items": [gen_item(p) for p in folder.glob("*") if path_filter(p)],
    }
get_folder_list.default_opt = {"only_dir": True, "fallbacks": []}

jrpc.add_method(M.read_wallpaper_config)
jrpc.add_method(M.write_wallpaper_config)
jrpc.add_method(M.reset_wallpaper_config)

@jrpc.add_method
def get_audio() -> list:
    """Return the latest 128-bin FFT spectrum as floats in [0, 1]."""
    return _audio_data


@jrpc.add_method
def list_audio_sources() -> list:
    """Return available PipeWire/PulseAudio monitor sources for the dropdown.
    System Default (auto-detect) is always first."""
    sources = [{"value": "", "label": "System Default (auto-detect)"}]
    try:
        result = subprocess.run(
            ['pactl', 'list', 'short', 'sources'],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2 and '.monitor' in parts[1]:
                sources.append({"value": parts[1], "label": parts[1]})
    except Exception:
        pass
    return sources


@jrpc.add_method
def set_audio_source(source: str) -> None:
    """Set the audio capture source and trigger an immediate restart of the loop."""
    global _audio_source_config, _audio_restart_requested
    _audio_source_config = source
    _audio_restart_requested = True


@jrpc.add_method
def delete_wallpaper(path: str, workshopid: str = "") -> dict:
    # Safety: require the target to be an existing directory containing
    # a project.json file so arbitrary paths can't be wiped out.
    try:
        folder: Path = Path(path).resolve()
        if not folder.is_dir():
            return {"ok": False, "error": "not a directory"}
        if not (folder / "project.json").is_file():
            return {"ok": False, "error": "not a wallpaper folder"}
        shutil.rmtree(folder)
        if workshopid:
            M.delete_wallpaper_config(workshopid)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


async def connect(uri):
    async with websockets.connect(uri) as websocket:
        while True:
            recv: str = jrpc.handle(await websocket.recv())
            await websocket.send(recv)

async def _main(uri: str) -> None:
    import signal
    loop = asyncio.get_running_loop()
    audio_task = None
    if _NUMPY_OK:
        audio_task = asyncio.create_task(_audio_capture_loop())

    # Cancel all tasks on SIGTERM so the audio task's finally block runs,
    # killing parec before this process exits.
    def _on_sigterm():
        for t in asyncio.all_tasks(loop):
            t.cancel()
    loop.add_signal_handler(signal.SIGTERM, _on_sigterm)

    try:
        await connect(uri)
    finally:
        if audio_task is not None and not audio_task.done():
            audio_task.cancel()
            try:
                await audio_task
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    import argparse

    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="qml localfile helper"
    )
    parser.add_argument("url", metavar="URL", type=str, help="a websocket url")
    args: dict = vars(parser.parse_args())

    if hasattr(asyncio, "run"):
        asyncio.run(_main(args["url"]))
    else:
        asyncio.get_event_loop().run_until_complete(_main(args["url"]))
