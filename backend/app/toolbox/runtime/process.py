import os
import subprocess
import time


class Cancelled(Exception):
    pass


def command(args, workdir, check, timeout=600, env=None, error_mapper=None):
    # No shell interpolation. Output goes to a bounded job-local file, never to API errors.
    log = workdir / "process.log"
    with log.open("wb") as output:
        proc = subprocess.Popen(args, cwd=workdir, stdout=output, stderr=output, env=env, start_new_session=True)
        deadline = time.monotonic() + timeout
        try:
            while proc.poll() is None:
                check()
                if time.monotonic() > deadline:
                    raise ValueError("执行超时，请缩短输入或稍后重试")
                if log.stat().st_size > 5 * 1024 * 1024:
                    raise ValueError("工具输出异常，已停止任务")
                # Enforce local output budget, including partial downloads.
                if sum(p.stat().st_size for p in workdir.iterdir() if p.is_file()) > 220 * 1024 * 1024:
                    raise ValueError("媒体处理超过临时空间限制")
                time.sleep(0.3)
            if proc.returncode:
                if error_mapper:
                    with log.open("rb") as diagnostic:
                        diagnostic.seek(max(0, log.stat().st_size - 32768))
                        raise error_mapper(diagnostic.read().decode("utf-8", errors="replace"))
                raise ValueError("工具执行失败，请检查输入格式、链接是否公开或站点访问限制")
        finally:
            if proc.poll() is None:
                import signal

                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                except ProcessLookupError:
                    proc.wait()
