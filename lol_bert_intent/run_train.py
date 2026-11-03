"""
一键训练启动脚本
直接运行即可开始训练，无需通过 PowerShell。

用法:
    python run_train.py
"""

import sys
import os

# 确保项目根目录在 sys.path 中，方便直接 python run_train.py 调用
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from lol_intent.train import main

if __name__ == "__main__":
    # 覆盖默认参数，等价于原来的 train_sample_conda.ps1
    sys.argv = [
        "run_train.py",
        "--data", "data/intents_binary.csv",
        "--epochs", "5",
        "--batch-size", "8",
        "--output-dir", "models/lol-bert-binary-intent",
    ]
    main()
