"""
This provides a simple MCP server for managing notes.
Notes are stored in memory and can be added, searched.
"""

import sys
import logging
from typing import Union
from fastmcp import FastMCP

# configure logger
logger = logging.getLogger("mcp.notes")
h = logging.StreamHandler(sys.stderr)
h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logger.addHandler(h)
logger.setLevel(logging.INFO)
logger.propagate = False

# create MCP server
mcp = FastMCP("notes")

# initialize notes in memory
_NOTES: list[str] = []


@mcp.tool
def add_note(note: str) -> dict[str, int]:
    """Add a note to the notes list.

    Args:
        note: The note to add.

    Returns:
        A dictionary containing the index of the note and the total number of notes.
    """
    logger.debug("Adding note: %s", note)
    _NOTES.append(note)
    logger.debug("Note added: %s", note)
    return {"index": len(_NOTES) - 1, "total": len(_NOTES)}


@mcp.tool
def search_notes(query: str, top_k: int) -> dict[str, Union[list[str], int]]:
    """Search for notes matching the query.

    Args:
        query: The query to search for.
        top_k: The number of top matches to return.

    Returns:
        A dictionary containing the matches and the total number of matches.
    """
    logger.debug("Searching for notes: query=%s, top_k=%s", query, top_k)
    hits = [t for t in _NOTES if query.lower() in t.lower()]
    logger.debug("Search results: %s", hits)
    return {"matches": hits[:top_k], "count": len(hits)}


@mcp.tool
def get_notes() -> dict[str, list[str]]:
    """Get all notes.

    Returns:
        A dictionary containing the notes.
    """
    logger.debug("Getting all notes...")
    notes = _NOTES
    logger.debug("Total count: %s", len(notes))
    return {"notes": notes}


if __name__ == "__main__":
    logger.debug("MCP notes server starting...")
    mcp.run(transport="stdio")
