from __future__ import annotations

import argparse
import json

from .predictor import LolIntentPredictor


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict LOL intent from text.")
    parser.add_argument("text")
    parser.add_argument("--model-dir", default="models/lol-bert-binary-intent")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    predictor = LolIntentPredictor(args.model_dir)
    result = predictor.predict(args.text, top_k=args.top_k)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
