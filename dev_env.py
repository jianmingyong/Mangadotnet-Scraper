import subprocess
import sys


def install():
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", ".[dev]"])


if __name__ == "__main__":
    install()
