import sys
import logging
from fastmcp import FastMCP

# add logger for debugging
logger = logging.getLogger("mcp.demo")
logger.setLevel(logging.DEBUG)

# add stderr handler
_handler = logging.StreamHandler(sys.stderr)
_handler.setLevel(logging.DEBUG)
_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logger.addHandler(_handler)

# prevent propagation to root logger
logger.propagate = False

mcp = FastMCP("demo")


@mcp.tool
def add(a: int, b: int) -> int:
    logger.debug("add called with a=%s, b=%s", a, b)
    result = a + b
    logger.debug("add result=%s", result)
    return result


if __name__ == "__main__":
    logger.debug("MCP server starting...")
    mcp.run(transport="stdio")
    logger.debug("MCP server stopped.")
