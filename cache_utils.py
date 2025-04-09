import time
import functools
import cachetools.func
from flask import request

# In-memory cache for responses
response_cache = {}
response_cache_size = 1000  # Maximum cache entries
response_cache_hits = 0
response_cache_misses = 0

# Simple LRU cache for file content
file_content_cache = cachetools.func.lru_cache(maxsize=100)

# Caching decorator for route responses
def cached_response(timeout=300):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            global response_cache, response_cache_hits, response_cache_misses
            
            # Skip cache for authenticated/session routes
            if 'X-Session-Id' in request.headers or 'X-API-Key' in request.headers:
                return f(*args, **kwargs)
            
            # Create a cache key from the request path and query string
            cache_key = f"{request.path}?{request.query_string.decode('utf-8')}"
            
            # Check if we have a cached response and it's still valid
            if cache_key in response_cache:
                cached_item = response_cache[cache_key]
                if time.time() - cached_item['timestamp'] < timeout:
                    response_cache_hits += 1
                    return cached_item['response']
            
            # Cache miss - call the original function
            response_cache_misses += 1
            response = f(*args, **kwargs)
            
            # Cache the response
            response_cache[cache_key] = {
                'response': response,
                'timestamp': time.time()
            }
            
            # Limit cache size by removing oldest entries if needed
            if len(response_cache) > response_cache_size:
                # Get the oldest cache key
                oldest_key = min(response_cache.keys(), 
                                key=lambda k: response_cache[k]['timestamp'])
                # Remove it
                del response_cache[oldest_key]
            
            return response
        return decorated_function
    return decorator
