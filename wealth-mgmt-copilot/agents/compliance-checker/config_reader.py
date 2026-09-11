"""
Configuration reader for Compliance Checker Fargate Agent
Reads configuration from config/config.conf
"""
import os
import configparser
from pathlib import Path


class ConfigReader:
    """Read configuration from config.conf file"""

    def __init__(self, config_path=None):
        self.config = configparser.ConfigParser()

        if config_path:
            config_file = Path(config_path)
        else:
            possible_paths = [
                Path(__file__).parent / 'config' / 'config.conf',
                Path(__file__).parent.parent.parent / 'config' / 'config.conf',
                Path('config/config.conf'),
                Path('../../config/config.conf'),
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
        env_key = f"{section.upper()}_{key.upper()}"
        env_value = os.environ.get(env_key)
        if env_value:
            return env_value
        return self.config.get(section, key, fallback=fallback)

    def get_int(self, section, key, fallback=0):
        """Get integer configuration value"""
        env_key = f"{section.upper()}_{key.upper()}"
        env_value = os.environ.get(env_key)
        if env_value:
            return int(env_value)
        return self.config.getint(section, key, fallback=fallback)

    def get_float(self, section, key, fallback=0.0):
        """Get float configuration value"""
        env_key = f"{section.upper()}_{key.upper()}"
        env_value = os.environ.get(env_key)
        if env_value:
            return float(env_value)
        return self.config.getfloat(section, key, fallback=fallback)

    def get_aws_region(self):
        """Get AWS region from config or environment"""
        region = os.environ.get('AWS_REGION')
        if region:
            return region
        region = os.environ.get('AWS_DEFAULT_REGION')
        if region:
            return region
        return self.get('AWS', 'region', fallback='us-west-2')

    def get_dynamodb_tables(self):
        """Get DynamoDB table names"""
        return {
            'client_profiles': self.get('DynamoDB', 'table_client_profiles',
                                        fallback='wealth_mgmt_client_profiles'),
            'transactions': self.get('DynamoDB', 'table_transactions',
                                     fallback='wealth_mgmt_transactions'),
            'compliance_records': self.get('DynamoDB', 'table_compliance_records',
                                           fallback='wealth_mgmt_compliance_records'),
            'audit_log': self.get('DynamoDB', 'table_audit_log',
                                  fallback='wealth_mgmt_audit_log'),
            'user_auth': self.get('DynamoDB', 'table_user_auth',
                                  fallback='wealth_mgmt_user_auth'),
        }

    def get_compliance_agent_config(self):
        """Get Compliance Checker Agent specific configuration"""
        return {
            'project_name': self.get('ComplianceAgent', 'project_name',
                                     fallback='compliance-checker'),
            'cluster_name': self.get('ComplianceAgent', 'cluster_name',
                                     fallback='compliance-checker-cluster'),
            'service_name': self.get('ComplianceAgent', 'service_name',
                                     fallback='compliance-checker-service'),
            'ecr_repo_name': self.get('ComplianceAgent', 'ecr_repo_name',
                                      fallback='compliance-checker'),
            'log_group': self.get('ComplianceAgent', 'log_group',
                                  fallback='/ecs/compliance-checker'),
            'service_name_full': self.get('ComplianceAgent', 'service_name_full',
                                          fallback='compliance-checker-agent-fargate'),
            'agentcore_log_group': self.get('ComplianceAgent', 'agentcore_log_group',
                                            fallback='/aws/bedrock-agentcore/runtimes/compliance-checker-agent'),
            's3_bucket_prefix': self.get('ComplianceAgent', 's3_bucket_prefix',
                                         fallback='compliance-checker-build'),
            'model_id': self.get('ComplianceAgent', 'compliance_model_id',
                                 fallback='us.anthropic.claude-haiku-4-5-20251001-v1:0'),
        }

    def get_compliance_rules(self):
        """Get compliance threshold rules"""
        return {
            'max_single_transaction': self.get_int('ComplianceRules', 'max_single_transaction',
                                                    fallback=50000),
            'max_daily_volume': self.get_int('ComplianceRules', 'max_daily_volume',
                                              fallback=250000),
            'max_position_concentration': self.get_int('ComplianceRules', 'max_position_concentration',
                                                        fallback=25),
            'kyc_renewal_days': self.get_int('ComplianceRules', 'kyc_renewal_days',
                                              fallback=365),
            'pattern_detection_window_days': self.get_int('ComplianceRules', 'pattern_detection_window_days',
                                                           fallback=7),
            'aml_structuring_threshold': self.get_int('ComplianceRules', 'aml_structuring_threshold',
                                                       fallback=10000),
            'wash_sale_lookback_days': self.get_int('ComplianceRules', 'wash_sale_lookback_days',
                                                     fallback=30),
        }


_config_reader = None

def get_config():
    """Get singleton config reader instance"""
    global _config_reader
    if _config_reader is None:
        _config_reader = ConfigReader()
    return _config_reader
