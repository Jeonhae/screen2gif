import os
import importlib.util

utils_path = r"d:\myCode\screen2gif\utils.py"
spec = importlib.util.spec_from_file_location("utils", utils_path)
utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(utils)
shrink_gif_to_target = utils.shrink_gif_to_target

src = r"d:\myCode\screen2gif\gif\20260204_143332.gif"
out = r"d:\myCode\screen2gif\smallGif"
print("source:", src)
res = shrink_gif_to_target(src, 10 * 1024 * 1024, out)
print("result:", res)
if res:
    print("size:", os.path.getsize(res))
