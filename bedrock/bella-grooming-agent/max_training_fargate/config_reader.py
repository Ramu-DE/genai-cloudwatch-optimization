"""
Configuration reader for Max Fargate Agent
Reads configuration from config/config.conf
"""
import os
import configparser
from pathlib import Path


class ConfigReader:
    """Read configuration from config.conf file"""
    
    def __init__(self, config_path=None):
        """
        Initialize config reader
        
        Args:
            config_path: Path to config.conf file. If None, searches in standard locations.
        """
        self.config = configparser.ConfigParser()
        
        # Find config file
        if config_path:
            config_file = Path(config_path)
        else:
            # Try multiple locations
            possible_paths = [
                Path(__file__).parent.parent.parent / 'config' / 'config.conf',  # From agents/Max_fargate
                Path('config/config.conf'),  # From project root
                Path('../../config/config.conf'),  # Relative
            ]
            
            config_file = None
            for path in possible_paths:
                if path.exists():
                    config_file = path
                    break
            
            if not config_file:
                raise FileNotFoundError(
                    "config.conf not found. Searched in: " + 
                    ", ".join(str(p) for p in possible_paths)
                )
        
        self.config.read(config_file)
    
    def get(self, section, key, fallback=None):
        """Get configuration value with environment variable override"""
        # Check environment variable first (format: SECTION_KEY)
        env_key = f"{section.upper()}_{key.upper()}"
        env_value = os.environ.get(env_key)
        if env_value:
            return env_value
        
        # Fall back to config file
        return self.config.get(section, key, fallback=fallback)
    
    def get_aws_region(self):
        """Get AWS region from config or environment"""
        # Check AWS_REGION env var first
        region = os.environ.get('AWS_REGION')
        if region:
            return region
        
        # Check AWS_DEFAULT_REGION
        region = os.environ.get('AWS_DEFAULT_REGION')
        if region:
            return region
        
        # Fall back to config file
        return self.get('AWS', 'region', fallback='us-west-2')
    
    def get_dynamodb_tables(self):
        """Get DynamoDB table names"""
        return {
            'customers': self.get('DynamoDB', 'table_customer_profiles', 
                                 fallback='genai_petstore_customer_profiles'),
            'appointments': self.get('DynamoDB', 'table_appointments', 
                                    fallback='genai_petstore_appointments'),
            'user_auth': self.get('DynamoDB', 'table_user_auth', 
                                 fallback='genai_petstore_user_auth')
        }
    
    def get_max_agent_config(self):
        """Get Max Agent specific configuration"""
        return {
            'project_name': self.get('MaxAgent', 'project_name', fallback='max-agent'),
            'cluster_name': self.get('MaxAgent', 'cluster_name', fallback='max-agent-cluster'),
            'service_name': self.get('MaxAgent', 'service_name', fallback='max-agent-service'),
            'ecr_repo_name': self.get('MaxAgent', 'ecr_repo_name', fallback='max-agent'),
            'log_group': self.get('MaxAgent', 'log_group', fallback='/ecs/max-agent'),
            'service_name_full': self.get('MaxAgent', 'service_name_full', 
                                         fallback='max-training-agent'),
            'agentcore_log_group': self.get('MaxAgent', 'agentcore_log_group', 
                                           fallback='/aws/bedrock-agentcore/runtimes/max-training-agent'),
            's3_bucket_prefix': self.get('MaxAgent', 's3_bucket_prefix', 
                                        fallback='max-agent-build'),
            'model_id': self.get('MaxAgent', 'max_model_id', 
                                fallback='us.anthropic.claude-haiku-4-5-20251001-v1:0')
        }


# Singleton instance
_config_reader = None

def get_config():
    """Get singleton config reader instance"""
    global _config_reader
    if _config_reader is None:
        _config_reader = ConfigReader()
    return _config_reader
