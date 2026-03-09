"""
Web Search Module for Footprint Specifications

Searches the internet for real-world PCB footprint specifications,
datasheets, and IPC-7351 standards to ensure accurate footprint generation.
"""
import logging
from typing import List, Dict, Any, Optional
import time

logger = logging.getLogger(__name__)


# Global reference to the actual web_search tool (set by caller)
_web_search_tool = None

def set_web_search_tool(tool):
    """Set the actual web_search tool to use"""
    global _web_search_tool
    _web_search_tool = tool
    if tool:
        logger.info("Web search tool set - will perform actual web searches")
    else:
        logger.warning("Web search tool cleared")

def web_search(search_term: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search the web for footprint specifications and datasheets.
    
    This function attempts to use the web_search tool available in the environment
    to search for real-world footprint specifications. If the tool is not available,
    it returns an empty list.
    
    This function is designed to work in two ways:
    1. If called from within Cursor's agent context, it will use the web_search tool
    2. If the tool is not available, it returns empty results and the LLM will use its knowledge
    
    Args:
        search_term: The search query string
        num_results: Number of results to return (default: 5)
    
    Returns:
        List of search results with 'title', 'url', and 'snippet' keys
    """
    try:
        logger.info(f"Attempting web search for: {search_term}")
        
        # First, try the explicitly set tool
        if _web_search_tool and callable(_web_search_tool):
            try:
                results = _web_search_tool(search_term, num_results)
                if results:
                    logger.info(f"Web search returned {len(results)} results using set tool")
                    return results
            except Exception as e:
                logger.warning(f"Web search tool call failed: {e}")
        
        # Try to use the web_search tool from the environment
        # This could be available through Cursor's tool calling interface
        # We'll try to detect it dynamically by checking multiple sources
        try:
            import sys
            import inspect
            
            # Method 1: Look for web_search in the calling frame's globals
            frame = inspect.currentframe()
            if frame and frame.f_back:
                caller_globals = frame.f_back.f_globals
                if 'web_search' in caller_globals and callable(caller_globals['web_search']):
                    tool_func = caller_globals['web_search']
                    # Make sure it's not this function itself
                    if tool_func is not web_search:
                        logger.info(f"Found web_search tool in caller's globals, using it")
                        results = tool_func(search_term, num_results)
                        if results:
                            logger.info(f"Web search returned {len(results)} results")
                            return results
            
            # Method 2: Check if web_search is in the module's globals (might be injected)
            if 'web_search' in globals() and callable(globals()['web_search']):
                tool_func = globals()['web_search']
                # Make sure it's not this function itself
                if tool_func is not web_search:
                    logger.info(f"Found web_search tool in module globals, using it")
                    results = tool_func(search_term, num_results)
                    if results:
                        logger.info(f"Web search returned {len(results)} results")
                        return results
            
            # Method 3: Try to get from builtins
            if hasattr(__builtins__, 'web_search'):
                tool_func = getattr(__builtins__, 'web_search')
                if callable(tool_func) and tool_func is not web_search:
                    logger.info(f"Found web_search tool in builtins, using it")
                    results = tool_func(search_term, num_results)
                    if results:
                        logger.info(f"Web search returned {len(results)} results")
                        return results
        except Exception as e:
            logger.debug(f"Could not access web_search tool: {e}")
        
        # If web_search tool is not available, return empty
        logger.warning(f"Web search tool not available for '{search_term}', returning empty results")
        return []
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return []


def search_footprint_specifications(footprint_name: str, lib_reference: str = "", 
                                   component_type: str = "", web_search_func=None) -> str:
    """
    Search for comprehensive footprint specifications and return formatted results.
    
    Generates multiple search queries to find:
    1. IPC-7351 standard specifications
    2. Manufacturer datasheets
    3. Package dimensions and pad layouts
    4. Pin pitch and spacing information
    
    Args:
        footprint_name: The footprint/package name (e.g., "ESOP8L", "TO-263-7")
        lib_reference: Component library reference (e.g., "LM7805")
        component_type: Component type (e.g., "ic", "transistor")
        web_search_func: Optional web search function to use (if None, tries to find it)
    
    Returns:
        Formatted string with actual search results (if available) or search instructions
    """
    search_queries = []
    
    # Primary search: IPC-7351 standard for the package
    search_queries.append(f"{footprint_name} IPC-7351 footprint dimensions pad layout specifications")
    
    # Secondary search: Package dimensions
    search_queries.append(f"{footprint_name} package dimensions pin pitch pad size datasheet")
    
    # If we have a component reference, search for its datasheet
    if lib_reference:
        search_queries.append(f"{lib_reference} {footprint_name} datasheet package specifications")
    
    # Search for specific package type information
    if component_type:
        search_queries.append(f"{footprint_name} {component_type} package specifications")
    
    # Try to perform actual web searches
    all_search_results = []
    search_func = web_search_func or web_search
    
    if search_func and callable(search_func):
        logger.info(f"Performing web searches for footprint: {footprint_name}")
        for query in search_queries:
            try:
                results = search_func(query, num_results=3)
                if results:
                    all_search_results.extend(results)
                    logger.info(f"Found {len(results)} results for query: {query}")
            except Exception as e:
                logger.debug(f"Web search failed for query '{query}': {e}")
                continue
    
    # Format the results
    if all_search_results:
        # We have actual search results - format them for the LLM
        formatted_results = "WEB SEARCH RESULTS (REAL-WORLD SPECIFICATIONS):\n\n"
        for i, result in enumerate(all_search_results[:10], 1):  # Limit to top 10 results
            title = result.get('title', 'No title')
            url = result.get('url', '')
            snippet = result.get('snippet', result.get('content', ''))
            
            formatted_results += f"Result {i}:\n"
            formatted_results += f"Title: {title}\n"
            if url:
                formatted_results += f"URL: {url}\n"
            if snippet:
                # Truncate long snippets
                snippet_text = snippet[:500] + "..." if len(snippet) > 500 else snippet
                formatted_results += f"Content: {snippet_text}\n"
            formatted_results += "\n"
        
        formatted_results += """
CRITICAL INSTRUCTIONS:
1. Extract EXACT dimensions from the search results above (pad sizes, pin pitch, row spacing, etc.)
2. Use the EXACT values from search results - do NOT approximate or round
3. If multiple sources provide dimensions, use the most authoritative (IPC-7351 > manufacturer datasheet > other)
4. Combine search results with your knowledge of IPC-7351B/C standards
5. Generate the footprint using the REAL-WORLD specifications found in search results
"""
        return formatted_results
    else:
        # No search results available - provide instructions for LLM to use its knowledge
        search_instructions = f"""
IMPORTANT: Use your knowledge of IPC-7351B/C standards, JEDEC standards, and manufacturer datasheets to determine EXACT dimensions.

Recommended search queries (if you have web search capability):
{chr(10).join(f'  {i+1}. "{q}"' for i, q in enumerate(search_queries))}

What to look for:
1. IPC-7351 standard dimensions (pad sizes, spacing, pitch)
2. Manufacturer datasheet package drawings
3. Pin layout and numbering conventions
4. Thermal pad dimensions (if applicable)
5. Row spacing for dual-row packages
6. Exact pad positions and coordinates

CRITICAL: Use EXACT dimensions from your knowledge of industry standards - do not approximate or round.
"""
    return search_instructions
