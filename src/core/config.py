import os
import sys

# Configuration
class Config:
    def __init__(self):
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        
        # Determine if we're using dynamic keys (client's OpenAI key)
        self.use_dynamic_openai_key = not self.openai_api_key
        
        # Add Anthropic API key for client validation
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.anthropic_api_key:
            print("Warning: ANTHROPIC_API_KEY not set. Client API key validation will be disabled.")
        
        self.openai_base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.azure_api_version = os.environ.get("AZURE_API_VERSION")  # For Azure OpenAI
        self.host = os.environ.get("HOST", "0.0.0.0")
        self.port = int(os.environ.get("PORT", "8082"))
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        self.max_tokens_limit = int(os.environ.get("MAX_TOKENS_LIMIT", "4096"))
        self.min_tokens_limit = int(os.environ.get("MIN_TOKENS_LIMIT", "100"))
        
        # Connection settings
        self.request_timeout = int(os.environ.get("REQUEST_TIMEOUT", "90"))
        self.max_retries = int(os.environ.get("MAX_RETRIES", "2"))
        
        # Model settings - BIG and SMALL models
        self.big_model = os.environ.get("BIG_MODEL", "gpt-4o")
        self.middle_model = os.environ.get("MIDDLE_MODEL", self.big_model)
        self.small_model = os.environ.get("SMALL_MODEL", "gpt-4o-mini")
        
    def validate_api_key(self):
        """Basic API key validation"""
        # If using dynamic keys, we don't need to validate a fixed key
        if self.use_dynamic_openai_key:
            return True
            
        if not self.openai_api_key:
            return False
        # Basic format check for OpenAI API keys
        if not self.openai_api_key.startswith('sk-'):
            return False
        return True
        
    def validate_client_api_key(self, client_api_key):
        """Validate client's API key"""
        # If no ANTHROPIC_API_KEY is set in the environment, skip validation
        if not self.anthropic_api_key:
            return True
            
        # When using dynamic OpenAI keys, validate the key format instead
        if self.use_dynamic_openai_key:
            # Basic format check for OpenAI API keys
            return client_api_key and client_api_key.startswith('sk-')
            
        # Check if the client's API key matches the expected value
        return client_api_key == self.anthropic_api_key

try:
    config = Config()
    if config.use_dynamic_openai_key:
        print(f"\033[34m Configuration loaded: Using dynamic client keys, BASE_URL='{config.openai_base_url}'")
    else:
        print(f"\033[34m Configuration loaded: API_KEY={'*' * 20}..., BASE_URL='{config.openai_base_url}'")
except Exception as e:
    print(f"=4 Configuration Error: {e}")
    sys.exit(1)
