import sys
import io
import logging
import pathlib
import re
from typing import Any
from fastmcp import FastMCP
from pydantic import BaseModel, Field

# configure logger
logger = logging.getLogger("mcp.files")
h = logging.StreamHandler(sys.stderr)
h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger.addHandler(h)
logger.setLevel(logging.INFO)
logger.propagate = False

# create MCP server
mcp = FastMCP("files")

# configure whitelist
WHITELIST = [(pathlib.Path(__file__).parent.parent.parent / "documents").resolve()]


def _resolve_safe(path: str) -> pathlib.Path:
    """Resolve a path safely.

    Args:
        path: The path to resolve.

    Returns:
        The resolved path.
    """
    logger.debug("Resolving path: %s", path)
    p = pathlib.Path(path).expanduser().resolve()
    if not any(str(p).startswith(str(w)) for w in WHITELIST):
        raise ValueError("Path not allowed")
    logger.debug("Resolved path: %s", p)
    return p


class ListFilesArgs(BaseModel):
    dir_path: str = Field(description="The path to the directory to list files from.")
    pattern: str | None = Field(
        default=None, description="The pattern to filter files by."
    )
    max_files: int = Field(
        default=100, description="The maximum number of files to list."
    )


class ListFilesResult(BaseModel):
    count: int = Field(description="The number of files that were listed.")
    files: list[str] = Field(description="The files that were listed.")


@mcp.tool
def list_files(args: ListFilesArgs) -> ListFilesResult:
    """List files in a directory."""

    logger.debug(
        "Listing files: dir_path=%s, pattern=%s, max_files=%s",
        args.dir_path,
        args.pattern,
        args.max_files,
    )
    d = _resolve_safe(args.dir_path)
    out = []
    rx = re.compile(args.pattern) if args.pattern else None
    for p in d.rglob("*"):
        if p.is_file() and (rx is None or rx.search(p.name)):
            out.append(str(p))
            if len(out) >= args.max_files:
                break
    logger.debug("Listed files: count=%s, files=%s", len(out), out)
    return ListFilesResult(count=len(out), files=out)


class ReadTextArgs(BaseModel):
    path: str = Field(description="The path to the file to read.")
    length: int | None = Field(
        default=None,
        description="The length to read. If not provided, the entire file will be read.",
    )
    encoding: str = Field(
        default="utf-8", description="The encoding to use to read the file."
    )
    start: int = Field(default=0, description="The start position to read from.")


class ReadTextResult(BaseModel):
    path: str = Field(description="The path to the file that was read.")
    start: int = Field(description="The start position that was read from.")
    length: int = Field(description="The length that was read.")
    content: str = Field(description="The content that was read.")


@mcp.tool
def read_text(args: ReadTextArgs) -> ReadTextResult:
    """Read a text file safely."""

    logger.debug(
        "Reading text: path=%s, encoding=%s, start=%s, length=%s",
        args.path,
        args.encoding,
        args.start,
        args.length,
    )
    p = _resolve_safe(args.path)

    with io.open(p, "r", encoding=args.encoding, errors="replace") as f:
        f.seek(args.start)
        data = f.read(args.length) if args.length is not None else f.read()

    logger.debug(
        "Read text: path=%s, start=%s, length=%s, content=%s",
        str(p),
        args.start,
        len(data),
        data,
    )
    return ReadTextResult(path=str(p), start=args.start, length=len(data), content=data)


class GrepArgs(BaseModel):
    path: str = Field(description="The path to the file to grep.")
    query: str = Field(description="The query to grep for.")
    max_hits: int = Field(
        default=20, description="The maximum number of hits to return."
    )


class GrepResult(BaseModel):
    path: str = Field(description="The path to the file that was grepped.")
    query: str = Field(description="The query that was grepped for.")
    hits: list[dict[str, Any]] = Field(description="The hits that were found.")


@mcp.tool
def grep(args: GrepArgs) -> GrepResult:
    """Grep a file for a query."""
    logger.debug(
        "Grepping file: path=%s, query=%s, max_hits=%s",
        args.path,
        args.query,
        args.max_hits,
    )
    p = _resolve_safe(args.path)
    hits = []
    with open(p, "r", errors="ignore") as f:
        for i, line in enumerate(f, 1):
            if args.query.lower() in line.lower():
                hits.append({"line": i, "text": line.rstrip("\n")})
                if len(hits) >= args.max_hits:
                    break
    logger.debug("Grepped file: path=%s, query=%s, hits=%s", str(p), args.query, hits)
    return GrepResult(path=str(p), query=args.query, hits=hits)


if __name__ == "__main__":
    logger.debug("MCP files server starting...")
    mcp.run(transport="stdio")
