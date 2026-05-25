import logging
import sys

logging.getLogger("ikuai-backup").setLevel(logging.DEBUG)

fmt = logging.Formatter(
    "%(asctime)s.%(msecs)03d | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.DEBUG)
console.setFormatter(fmt)

root = logging.getLogger("ikuai-backup")
root.addHandler(console)

logger = root
