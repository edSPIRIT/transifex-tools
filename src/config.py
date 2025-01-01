import os
from dotenv import load_dotenv

def load_config():
    """Load configuration from environment variables"""
    load_dotenv()
    
    config = {
        'api_token': os.getenv('TRANSIFEX_API_TOKEN'),
        'organization': os.getenv('TRANSIFEX_ORGANIZATION'),
        'project': os.getenv('TRANSIFEX_PROJECT'),
        'target_languages': os.getenv('TARGET_LANGUAGES', '').split(',')
    }
    
    # Validate required config
    missing = [k for k, v in config.items() if not v]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    return config 