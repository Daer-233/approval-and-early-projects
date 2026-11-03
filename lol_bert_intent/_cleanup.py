import os
import shutil

BASE = r"I:\AI_Develop\py_AI\lol_bert_intent"

to_delete_files = [
    "train_sample_conda.ps1",
    "start_mcp_conda.ps1",
    "start_mcp_sse_conda.ps1",
    "install_cpu.ps1",
    "mcp_stderr.log",
    "mcp_stdout.log",
    "data/intents_sample.csv",
]

to_delete_dirs = [
    "models/lol-bert-intent",
    ".venv",
]

for f in to_delete_files:
    path = os.path.join(BASE, f)
    if os.path.exists(path):
        os.remove(path)
        print(f"已删除: {f}")
    else:
        print(f"不存在: {f}")

for d in to_delete_dirs:
    path = os.path.join(BASE, d)
    if os.path.exists(path):
        shutil.rmtree(path)
        print(f"已删除: {d}")
    else:
        print(f"不存在: {d}")

# 删除 Python 3.14 的 pycache
pycache_dir = os.path.join(BASE, "lol_intent", "__pycache__")
if os.path.isdir(pycache_dir):
    for name in os.listdir(pycache_dir):
        if "cpython-314" in name:
            os.remove(os.path.join(pycache_dir, name))
            print(f"已删除: lol_intent/__pycache__/{name}")

print("\n全部清理完成。")
