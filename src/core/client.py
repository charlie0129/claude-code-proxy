import asyncio
import json
import time
import logging
from fastapi import HTTPException
from typing import Optional, AsyncGenerator, Dict, Any
from openai import AsyncOpenAI, AsyncAzureOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from openai._exceptions import APIError, RateLimitError, AuthenticationError, BadRequestError

logger = logging.getLogger(__name__)


class OpenAIClientManager:
    """Manages OpenAI client instances with LRU caching and automatic cleanup."""
    
    def __init__(self, max_clients: int = 50, client_ttl: int = 3600):
        self.max_clients = max_clients
        self.client_ttl = client_ttl
        self.clients = {}  # api_key -> client
        self.last_used = {}  # api_key -> timestamp
        self.lock = asyncio.Lock()
        self.cleanup_task = None
        self.metrics = {
            'clients_created': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'active_clients': 0,
            'clients_evicted': 0
        }
        self._cleanup_started = False
    
    def _start_cleanup_task(self):
        """Start the background cleanup task."""
        if not self._cleanup_started:
            self.cleanup_task = asyncio.create_task(self._cleanup())
            self._cleanup_started = True
    
    async def _cleanup(self):
        """Periodically clean up idle clients."""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self._cleanup_idle_clients()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in client cleanup task: {e}")
    
    async def _cleanup_idle_clients(self):
        """Remove clients that haven't been used for client_ttl seconds."""
        async with self.lock:
            now = time.time()
            expired_keys = []
            
            for key, last_used in self.last_used.items():
                if now - last_used > self.client_ttl:
                    expired_keys.append(key)
            
            for key in expired_keys:
                logger.info(f"Cleaning up idle client for key: {key[:10]}...")
                await self.clients[key].close()
                del self.clients[key]
                del self.last_used[key]
                self.metrics['clients_evicted'] += 1
    
    async def get_client(self, api_key: str, base_url: str, timeout: int = 90, 
                        api_version: Optional[str] = None) -> 'OpenAIClient':
        """Get or create a client for the given API key."""
        # Start cleanup task on first access
        if not self._cleanup_started:
            self._start_cleanup_task()
        
        async with self.lock:
            # Check cache hit
            if api_key in self.clients:
                self.metrics['cache_hits'] += 1
                self.last_used[api_key] = time.time()
                return self.clients[api_key]
            
            # Cache miss - create new client
            self.metrics['cache_misses'] += 1
            
            # Evict oldest if at max capacity
            if len(self.clients) >= self.max_clients:
                oldest_key = min(self.last_used.keys(), key=self.last_used.get)
                logger.info(f"Evicting oldest client for key: {oldest_key[:10]}...")
                await self.clients[oldest_key].close()
                del self.clients[oldest_key]
                del self.last_used[oldest_key]
                self.metrics['clients_evicted'] += 1
            
            # Create new client
            logger.info(f"Creating new client for key: {api_key[:10]}...")
            client = OpenAIClient(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                api_version=api_version
            )
            
            self.clients[api_key] = client
            self.last_used[api_key] = time.time()
            self.metrics['clients_created'] += 1
            self.metrics['active_clients'] = len(self.clients)
            
            return client
    
    async def close_all(self):
        """Close all client instances."""
        async with self.lock:
            for client in self.clients.values():
                await client.close()
            self.clients.clear()
            self.last_used.clear()
            self.metrics['active_clients'] = 0
        
        # Cancel cleanup task
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        return {
            **self.metrics,
            'cached_clients': len(self.clients),
            'max_clients': self.max_clients,
            'client_ttl': self.client_ttl
        }


class OpenAIClient:
    """Async OpenAI client with cancellation support."""
    
    def __init__(self, api_key: str, base_url: str, timeout: int = 90, api_version: Optional[str] = None):
        self.api_key = api_key
        self.base_url = base_url
        
        # Detect if using Azure and instantiate the appropriate client
        if api_version:
            self.client = AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=base_url,
                api_version=api_version,
                timeout=timeout
            )
        else:
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout
            )
        self.active_requests: Dict[str, asyncio.Event] = {}
    
    async def create_chat_completion(self, request: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
        """Send chat completion to OpenAI API with cancellation support."""
        
        # Create cancellation token if request_id provided
        if request_id:
            cancel_event = asyncio.Event()
            self.active_requests[request_id] = cancel_event
        
        try:
            # Create task that can be cancelled
            completion_task = asyncio.create_task(
                self.client.chat.completions.create(**request)
            )
            
            if request_id:
                # Wait for either completion or cancellation
                cancel_task = asyncio.create_task(cancel_event.wait())
                done, pending = await asyncio.wait(
                    [completion_task, cancel_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check if request was cancelled
                if cancel_task in done:
                    completion_task.cancel()
                    raise HTTPException(status_code=499, detail="Request cancelled by client")
                
                completion = await completion_task
            else:
                completion = await completion_task
            
            # Convert to dict format that matches the original interface
            return completion.model_dump()
        
        except AuthenticationError as e:
            raise HTTPException(status_code=401, detail=self.classify_openai_error(str(e)))
        except RateLimitError as e:
            raise HTTPException(status_code=429, detail=self.classify_openai_error(str(e)))
        except BadRequestError as e:
            raise HTTPException(status_code=400, detail=self.classify_openai_error(str(e)))
        except APIError as e:
            status_code = getattr(e, 'status_code', 500)
            raise HTTPException(status_code=status_code, detail=self.classify_openai_error(str(e)))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
        
        finally:
            # Clean up active request tracking
            if request_id and request_id in self.active_requests:
                del self.active_requests[request_id]
    
    async def create_chat_completion_stream(self, request: Dict[str, Any], request_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Send streaming chat completion to OpenAI API with cancellation support."""
        
        # Create cancellation token if request_id provided
        if request_id:
            cancel_event = asyncio.Event()
            self.active_requests[request_id] = cancel_event
        
        try:
            # Ensure stream is enabled
            request["stream"] = True
            if "stream_options" not in request:
                request["stream_options"] = {}
            request["stream_options"]["include_usage"] = True
            
            # Create the streaming completion
            streaming_completion = await self.client.chat.completions.create(**request)
            
            async for chunk in streaming_completion:
                # Check for cancellation before yielding each chunk
                if request_id and request_id in self.active_requests:
                    if self.active_requests[request_id].is_set():
                        raise HTTPException(status_code=499, detail="Request cancelled by client")
                
                # Convert chunk to SSE format matching original HTTP client format
                chunk_dict = chunk.model_dump()
                chunk_json = json.dumps(chunk_dict, ensure_ascii=False)
                yield f"data: {chunk_json}"
            
            # Signal end of stream
            yield "data: [DONE]"
                
        except AuthenticationError as e:
            raise HTTPException(status_code=401, detail=self.classify_openai_error(str(e)))
        except RateLimitError as e:
            raise HTTPException(status_code=429, detail=self.classify_openai_error(str(e)))
        except BadRequestError as e:
            raise HTTPException(status_code=400, detail=self.classify_openai_error(str(e)))
        except APIError as e:
            status_code = getattr(e, 'status_code', 500)
            raise HTTPException(status_code=status_code, detail=self.classify_openai_error(str(e)))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
        
        finally:
            # Clean up active request tracking
            if request_id and request_id in self.active_requests:
                del self.active_requests[request_id]

    def classify_openai_error(self, error_detail: Any) -> str:
        """Provide specific error guidance for common OpenAI API issues."""
        error_str = str(error_detail).lower()
        
        # Region/country restrictions
        if "unsupported_country_region_territory" in error_str or "country, region, or territory not supported" in error_str:
            return "OpenAI API is not available in your region. Consider using a VPN or Azure OpenAI service."
        
        # API key issues
        if "invalid_api_key" in error_str or "unauthorized" in error_str:
            return "Invalid API key. Please check your OPENAI_API_KEY configuration."
        
        # Rate limiting
        if "rate_limit" in error_str or "quota" in error_str:
            return "Rate limit exceeded. Please wait and try again, or upgrade your API plan."
        
        # Model not found
        if "model" in error_str and ("not found" in error_str or "does not exist" in error_str):
            return "Model not found. Please check your BIG_MODEL and SMALL_MODEL configuration."
        
        # Billing issues
        if "billing" in error_str or "payment" in error_str:
            return "Billing issue. Please check your OpenAI account billing status."
        
        # Default: return original message
        return str(error_detail)
    
    def cancel_request(self, request_id: str) -> bool:
        """Cancel an active request by request_id."""
        if request_id in self.active_requests:
            self.active_requests[request_id].set()
            return True
        return False
    
    async def close(self):
        """Close the underlying OpenAI client and cleanup resources."""
        if hasattr(self, 'client'):
            await self.client.close()
        
        # Cancel any active requests
        for request_id, cancel_event in self.active_requests.items():
            cancel_event.set()
        self.active_requests.clear()