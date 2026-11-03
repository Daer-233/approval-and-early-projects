from __future__ import annotations

import argparse
import os
from functools import lru_cache

from mcp.server.fastmcp import FastMCP

from .label_schema import LABEL_DESCRIPTIONS
from .predictor import LolIntentPredictor


DEFAULT_MODEL_DIR = os.getenv("LOL_INTENT_MODEL_DIR", "models/lol-bert-binary-intent")

mcp = FastMCP(
    "lol-intent-bert",
    instructions=(
        "LOL intent classifier. Use classify_lol_intent for League of Legends "
        "Chinese user query intent recognition."
    ),
    stateless_http=True,
    json_response=True,
    host=os.getenv("MCP_HOST", "0.0.0.0"),
    port=int(os.getenv("MCP_PORT", "8008")),
)


@lru_cache(maxsize=1)
def get_predictor() -> LolIntentPredictor:
    return LolIntentPredictor(DEFAULT_MODEL_DIR)


@mcp.tool()
def list_lol_intents() -> dict:
    """List supported LOL intent labels and Chinese descriptions."""
    return {"intents": LABEL_DESCRIPTIONS}


@mcp.tool()
def classify_lol_intent(text: str, top_k: int = 3) -> dict:
    """
    Classify a League of Legends user query into an intent label.

    Args:
        text: Chinese or mixed Chinese/English LOL user query.
        top_k: Number of candidate intents to return, from 1 to number of labels.
    """
    return get_predictor().predict(text=text, top_k=top_k)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LOL BERT intent MCP server.")
    parser.add_argument(
        "--transport",
        default=os.getenv("MCP_TRANSPORT", "sse"),
        choices=["stdio", "sse", "streamable-http"],
        help="Use sse (/sse) or streamable-http (/mcp) for Dify HTTP MCP; stdio for local MCP clients.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
