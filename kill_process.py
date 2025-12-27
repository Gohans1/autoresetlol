import os
import signal
import psutil


def kill_process_by_name(process_name):
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] == process_name:
                print(f"Killing {process_name} (PID: {proc.info['pid']})")
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


if __name__ == "__main__":
    kill_process_by_name("AntiFateEngine_v7.8.exe")
