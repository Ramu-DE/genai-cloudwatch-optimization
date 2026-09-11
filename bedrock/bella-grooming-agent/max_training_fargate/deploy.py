#!/usr/bin/env python3
"""
Automated Deployment Script for Max Training Agent to Fargate
Uses AWS CodeBuild for containerization and deployment
"""
import boto3
import json
import time
import sys
import os
import zipfile
import tempfile
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import config_reader
sys.path.insert(0, str(Path(__file__).parent))
from config_reader import get_config

class FargateDeployer:
    def __init__(self, region=None):
        # Load configuration
        self.config = get_config()
        self.region = region or self.config.get_aws_region()
        self.ecr = boto3.client('ecr', region_name=self.region)
        self.ecs = boto3.client('ecs', region_name=self.region)
        self.iam = boto3.client('iam', region_name=self.region)
        self.logs = boto3.client('logs', region_name=self.region)
        self.codebuild = boto3.client('codebuild', region_name=self.region)
        self.ec2 = boto3.client('ec2', region_name=self.region)
        self.sts = boto3.client('sts', region_name=self.region)
        self.s3 = boto3.client('s3', region_name=self.region)
        
        # Get account ID
        self.account_id = self.sts.get_caller_identity()['Account']
        
        # Load configuration from config.conf
        max_config = self.config.get_max_agent_config()
        self.project_name = max_config['project_name']
        self.cluster_name = max_config['cluster_name']
        self.service_name = max_config['service_name']
        self.ecr_repo_name = max_config['ecr_repo_name']
        self.log_group = max_config['log_group']
        self.service_name_full = max_config['service_name_full']
        self.agentcore_log_group = max_config['agentcore_log_group']
        self.s3_bucket_prefix = max_config['s3_bucket_prefix']
        
        # Get DynamoDB table configuration
        self.tables = self.config.get_dynamodb_tables()
        
        print("=" * 80)
        print("🚀 Max Training Agent - Automated Fargate Deployment")
        print("=" * 80)
        print(f"� Region:  {self.region}")
        print(f"🔑 Account ID: {self.account_id}")
        print("=" * 80)
    
    def create_ecr_repository(self):
        """Create ECR repository if it doesn't exist"""
        print("\n📦 Step 1: Creating ECR Repository...")
        try:
            response = self.ecr.describe_repositories(
                repositoryNames=[self.ecr_repo_name]
            )
            repo_uri = response['repositories'][0]['repositoryUri']
            print(f"✅ ECR repository already exists: {repo_uri}")
            return repo_uri
        except self.ecr.exceptions.RepositoryNotFoundException:
            response = self.ecr.create_repository(
                repositoryName=self.ecr_repo_name,
                imageScanningConfiguration={'scanOnPush': True},
                encryptionConfiguration={'encryptionType': 'AES256'}
            )
            repo_uri = response['repository']['repositoryUri']
            print(f"✅ Created ECR repository: {repo_uri}")
            return repo_uri
    
    def create_iam_roles(self):
        """Create IAM roles for ECS tasks"""
        print("\n🔐 Step 2: Creating IAM Roles...")
        
        # Trust policy for ECS tasks
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }
        
        # Create execution role
        execution_role_name = 'MaxAgentExecRole'
        try:
            self.iam.get_role(RoleName=execution_role_name)
            print(f"✅ Execution role already exists: {execution_role_name}")
        except self.iam.exceptions.NoSuchEntityException:
            self.iam.create_role(
                RoleName=execution_role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy)
            )
            self.iam.attach_role_policy(
                RoleName=execution_role_name,
                PolicyArn='arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy'
            )
            print(f"✅ Created execution role: {execution_role_name}")
        
        # Create task role
        task_role_name = 'MaxAgentTaskRole'
        try:
            self.iam.get_role(RoleName=task_role_name)
            print(f"✅ Task role already exists: {task_role_name}")
        except self.iam.exceptions.NoSuchEntityException:
            self.iam.create_role(
                RoleName=task_role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy)
            )
            
            # Task policy with Bedrock and DynamoDB permissions
            task_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "bedrock:InvokeModel",
                            "bedrock:InvokeModelWithResponseStream"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "dynamodb:GetItem",
                            "dynamodb:PutItem",
                            "dynamodb:Query",
                            "dynamodb:Scan",
                            "dynamodb:UpdateItem"
                        ],
                        "Resource": [
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{self.tables['customers']}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{self.tables['appointments']}",
                            f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{self.tables['user_auth']}"
                        ]
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "xray:PutTraceSegments",
                            "xray:PutTelemetryRecords"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "cloudwatch:PutMetricData",
                            "logs:PutLogEvents",
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:DescribeLogStreams",
                            "logs:DescribeLogGroups",
                            "xray:PutTraceSegments",
                            "xray:PutTelemetryRecords",
                            "ssm:GetParameters"
                        ],
                        "Resource": "*",
                        "Condition": {
                            "StringEquals": {
                                "cloudwatch:namespace": [
                                    "AWS/ApplicationSignals",
                                    "bedrock-agentcore"
                                ]
                            }
                        }
                    },
                    {
                        "Sid": "MarketplaceModelAccess",
                        "Effect": "Allow",
                        "Action": ["aws-marketplace:*"],
                        "Resource": "*"
                    }
                ]
            }
            
            self.iam.put_role_policy(
                RoleName=task_role_name,
                PolicyName='MaxAgentTaskPolicy',
                PolicyDocument=json.dumps(task_policy)
            )
            print(f"✅ Created task role: {task_role_name}")
        
        execution_role_arn = f"arn:aws:iam::{self.account_id}:role/{execution_role_name}"
        task_role_arn = f"arn:aws:iam::{self.account_id}:role/{task_role_name}"
        
        return execution_role_arn, task_role_arn
    
    def create_codebuild_project(self, repo_uri):
        """Create CodeBuild project for building and pushing Docker image"""
        print("\n🏗️  Step 3: Creating CodeBuild Project...")
        
        # Create CodeBuild service role
        codebuild_role_name = 'MaxAgentBuildRole'
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "codebuild.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }
        
        try:
            self.iam.get_role(RoleName=codebuild_role_name)
            print(f"✅ CodeBuild role already exists: {codebuild_role_name}")
        except self.iam.exceptions.NoSuchEntityException:
            self.iam.create_role(
                RoleName=codebuild_role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy)
            )
            
            # CodeBuild policy
            codebuild_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "ecr:GetAuthorizationToken",
                            "ecr:BatchCheckLayerAvailability",
                            "ecr:GetDownloadUrlForLayer",
                            "ecr:BatchGetImage",
                            "ecr:PutImage",
                            "ecr:InitiateLayerUpload",
                            "ecr:UploadLayerPart",
                            "ecr:CompleteLayerUpload"
                        ],
                        "Resource": "*"
                    },
                    {
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                            "s3:GetObjectVersion"
                        ],
                        "Resource": f"arn:aws:s3:::{self.s3_bucket_prefix}-{self.account_id}/*"
                    }
                ]
            }
            
            self.iam.put_role_policy(
                RoleName=codebuild_role_name,
                PolicyName='MaxAgentBuildPolicy',
                PolicyDocument=json.dumps(codebuild_policy)
            )
            print(f"✅ Created CodeBuild role: {codebuild_role_name}")
            
            # Wait for role to propagate
            print("⏳ Waiting for IAM role to propagate...")
            time.sleep(10)
        
        codebuild_role_arn = f"arn:aws:iam::{self.account_id}:role/{codebuild_role_name}"
        
        # Create CodeBuild project
        project_name = f"{self.project_name}-build"
        try:
            self.codebuild.delete_project(name=project_name)
            print(f"🗑️  Deleted existing CodeBuild project")
        except:
            pass
        
        # Inline buildspec
        buildspec = """version: 0.2

phases:
  pre_build:
    commands:
      - echo Logging in to Amazon ECR...
      - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com
      - REPOSITORY_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/$IMAGE_REPO_NAME
      - IMAGE_TAG=latest
      - echo Repository URI is $REPOSITORY_URI
      - echo Image tag is $IMAGE_TAG
      - echo Current directory is $(pwd)
      - echo Listing files...
      - ls -la
  build:
    commands:
      - echo Build started on `date`
      - echo Building the Docker image...
      - docker build --no-cache -t $IMAGE_REPO_NAME:$IMAGE_TAG .
      - docker tag $IMAGE_REPO_NAME:$IMAGE_TAG $REPOSITORY_URI:$IMAGE_TAG
  post_build:
    commands:
      - echo Build completed on `date`
      - echo Pushing the Docker image...
      - docker push $REPOSITORY_URI:$IMAGE_TAG
"""
        
        self.codebuild.create_project(
            name=project_name,
            source={
                'type': 'NO_SOURCE',
                'buildspec': buildspec
            },
            artifacts={'type': 'NO_ARTIFACTS'},
            environment={
                'type': 'LINUX_CONTAINER',
                'image': 'aws/codebuild/standard:7.0',
                'computeType': 'BUILD_GENERAL1_SMALL',
                'privilegedMode': True,
                'environmentVariables': [
                    {'name': 'AWS_DEFAULT_REGION', 'value': self.region},
                    {'name': 'AWS_ACCOUNT_ID', 'value': self.account_id},
                    {'name': 'IMAGE_REPO_NAME', 'value': self.ecr_repo_name},
                    {'name': 'IMAGE_TAG', 'value': 'latest'}
                ]
            },
            serviceRole=codebuild_role_arn
        )
        print(f"✅ Created CodeBuild project: {project_name}")
        
        return project_name
    
    def upload_source_to_s3(self):
        """Upload source code to S3 for CodeBuild"""
        print("\n📤 Step 4: Uploading Source Code to S3...")
        
        # Create S3 bucket for source code
        bucket_name = f"{self.s3_bucket_prefix}-{self.account_id}"
        try:
            # us-east-1 is special - it cannot have CreateBucketConfiguration
            if self.region == 'us-east-1':
                self.s3.create_bucket(Bucket=bucket_name)
            else:
                self.s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )
            print(f"✅ Created S3 bucket: {bucket_name}")
        except self.s3.exceptions.BucketAlreadyOwnedByYou:
            print(f"✅ S3 bucket already exists: {bucket_name}")
        except Exception as e:
            if 'BucketAlreadyExists' not in str(e):
                raise
        
        # Create zip file of current directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
            zip_path = tmp_file.name
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Essential files for Docker build
                essential_files = [
                    'app.py',
                    'config_reader.py',  # Required for configuration
                    'requirements.txt',
                    'Dockerfile',
                    '.dockerignore'
                ]
                
                for file in essential_files:
                    file_path = os.path.join(script_dir, file)
                    if os.path.exists(file_path):
                        zipf.write(file_path, file)
                        print(f"   Added: {file}")
                    else:
                        print(f"   ⚠️  Warning: {file} not found")
                
                # Also need to include config.conf from project root
                config_path = os.path.join(script_dir, '..', '..', 'config', 'config.conf')
                if os.path.exists(config_path):
                    # Add to config/ subdirectory in zip
                    zipf.write(config_path, 'config/config.conf')
                    print(f"   Added: config/config.conf")
                else:
                    print(f"   ⚠️  Warning: config/config.conf not found at {config_path}")
            
            # Upload to S3
            s3_key = 'source.zip'
            self.s3.upload_file(zip_path, bucket_name, s3_key)
            print(f"✅ Uploaded source code to s3://{bucket_name}/{s3_key}")
            
        finally:
            if os.path.exists(zip_path):
                os.unlink(zip_path)
        
        return bucket_name, s3_key
    
    def build_and_push_image(self, project_name, bucket_name, s3_key):
        """Trigger CodeBuild to build and push Docker image"""
        print("\n🐳 Step 5: Building and Pushing Docker Image with CodeBuild...")
        print("⏳ Starting CodeBuild... (this may take 3-5 minutes)")
        
        # Start build
        response = self.codebuild.start_build(
            projectName=project_name,
            sourceTypeOverride='S3',
            sourceLocationOverride=f"{bucket_name}/{s3_key}"
        )
        
        build_id = response['build']['id']
        print(f"📋 Build ID: {build_id}")
        
        # Wait for build to complete
        while True:
            response = self.codebuild.batch_get_builds(ids=[build_id])
            build = response['builds'][0]
            status = build['buildStatus']
            
            if status == 'IN_PROGRESS':
                print("⏳ Build in progress...")
                time.sleep(15)
            elif status == 'SUCCEEDED':
                print("✅ Docker image built and pushed successfully!")
                break
            else:
                print(f"❌ Build failed with status: {status}")
                
                # Try to get error details
                if 'phases' in build:
                    for phase in build['phases']:
                        if phase.get('phaseStatus') == 'FAILED':
                            print(f"\n❌ Failed phase: {phase['phaseType']}")
                            if 'contexts' in phase:
                                for context in phase['contexts']:
                                    print(f"   Error: {context.get('message', 'Unknown error')}")
                
                print(f"\n📋 Check full logs: https://console.aws.amazon.com/codesuite/codebuild/{self.region}/projects/{project_name}/history")
                sys.exit(1)
    
    def create_log_group(self):
        """Create CloudWatch log groups (ECS + AgentCore Runtime)"""
        print("\n📊 Step 6: Creating CloudWatch Log Groups...")
        
        # Create ECS log group
        try:
            self.logs.create_log_group(logGroupName=self.log_group)
            print(f"✅ Created ECS log group: {self.log_group}")
        except self.logs.exceptions.ResourceAlreadyExistsException:
            print(f"✅ ECS log group already exists: {self.log_group}")
        
        # Create AgentCore Runtime log group (required for agents outside AgentCore)
        agentcore_log_group = self.agentcore_log_group
        try:
            self.logs.create_log_group(logGroupName=agentcore_log_group)
            print(f"✅ Created AgentCore Runtime log group: {agentcore_log_group}")
        except self.logs.exceptions.ResourceAlreadyExistsException:
            print(f"✅ AgentCore Runtime log group already exists: {agentcore_log_group}")
    
    def create_ecs_cluster(self):
        """Create ECS cluster"""
        print("\n🎯 Step 7: Creating ECS Cluster...")
        try:
            # Check if cluster already exists
            existing_clusters = self.ecs.describe_clusters(clusters=[self.cluster_name])
            if existing_clusters['clusters'] and existing_clusters['clusters'][0]['status'] == 'ACTIVE':
                print(f"✅ ECS cluster already exists: {self.cluster_name}")
                return
            
            # Create ECS service-linked role if it doesn't exist
            try:
                self.iam.create_service_linked_role(
                    AWSServiceName='ecs.amazonaws.com',
                    Description='ECS service-linked role'
                )
                print("✅ Created ECS service-linked role")
                import time
                time.sleep(10)  # Wait for role propagation
            except self.iam.exceptions.InvalidInputException:
                # Role already exists
                print("✅ ECS service-linked role already exists")
            
            # Create cluster
            response = self.ecs.create_cluster(
                clusterName=self.cluster_name,
                capacityProviders=['FARGATE', 'FARGATE_SPOT']
            )
            print(f"✅ Created ECS cluster: {self.cluster_name}")
        except Exception as e:
            print(f"❌ Error creating ECS cluster: {e}")
            raise
    
    def register_task_definition(self, repo_uri, execution_role_arn, task_role_arn):
        """Register ECS task definition"""
        print("\n📝 Step 8: Registering Task Definition...")
        
        task_def = {
            "family": self.project_name,
            "networkMode": "awsvpc",
            "requiresCompatibilities": ["FARGATE"],
            "cpu": "2048",
            "memory": "4096",
            "executionRoleArn": execution_role_arn,
            "taskRoleArn": task_role_arn,
            "containerDefinitions": [
                {
                    "name": self.project_name,
                    "image": f"{repo_uri}:latest",
                    "portMappings": [
                        {
                            "containerPort": 8080,
                            "protocol": "tcp"
                        }
                    ],
                    "environment": [
                        {"name": "AWS_REGION", "value": self.region},
                        {"name": "AWS_DEFAULT_REGION", "value": self.region},
                        # Application Signals Configuration
                        {"name": "AGENT_OBSERVABILITY_ENABLED", "value": "true"},
                        {"name": "OTEL_PYTHON_DISTRO", "value": "aws_distro"},
                        {"name": "OTEL_PYTHON_CONFIGURATOR", "value": "aws_configurator"},
                        {"name": "OTEL_EXPORTER_OTLP_PROTOCOL", "value": "http/protobuf"},
                        {"name": "OTEL_TRACES_EXPORTER", "value": "otlp"},
                        # Point to CloudWatch agent sidecar on localhost
                        {"name": "OTEL_EXPORTER_OTLP_ENDPOINT", "value": "http://localhost:4316"},
                        {"name": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "value": "http://localhost:4316/v1/traces"},
                        {"name": "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "value": "http://localhost:4316/v1/metrics"},
                        # Service identification for Application Signals
                        {"name": "OTEL_RESOURCE_ATTRIBUTES", "value": f"service.name={self.service_name_full},aws.log.group.names={self.agentcore_log_group},cloud.resource_id={self.service_name_full}-fargate,deployment.environment=production"},
                        {"name": "OTEL_EXPORTER_OTLP_LOGS_HEADERS", "value": f"x-aws-log-group={self.agentcore_log_group},x-aws-log-stream=runtime-logs,x-aws-metric-namespace=bedrock-agentcore"},
                        {"name": "_AWS_XRAY_TRACING_NAME", "value": self.service_name_full},
                        # Application Signals service name (displayed in dashboards)
                        {"name": "OTEL_SERVICE_NAME", "value": self.service_name_full}
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": self.log_group,
                            "awslogs-region": self.region,
                            "awslogs-stream-prefix": "ecs"
                        }
                    },
                    "healthCheck": {
                        "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
                        "interval": 300,
                        "timeout": 5,
                        "retries": 3,
                        "startPeriod": 60
                    },
                    "dependsOn": [
                        {
                            "containerName": "cloudwatch-agent",
                            "condition": "START"
                        }
                    ]
                },
                # CloudWatch Agent Sidecar for Application Signals
                {
                    "name": "cloudwatch-agent",
                    "image": "public.ecr.aws/cloudwatch-agent/cloudwatch-agent:latest",
                    "essential": True,
                    "environment": [
                        {"name": "CW_CONFIG_CONTENT", "value": json.dumps({
                            "traces": {
                                "traces_collected": {
                                    "application_signals": {
                                        "enabled": True
                                    }
                                }
                            },
                            "logs": {
                                "metrics_collected": {
                                    "application_signals": {
                                        "enabled": True
                                    }
                                }
                            }
                        })}
                    ],
                    "logConfiguration": {
                        "logDriver": "awslogs",
                        "options": {
                            "awslogs-group": self.log_group,
                            "awslogs-region": self.region,
                            "awslogs-stream-prefix": "cloudwatch-agent"
                        }
                    }
                }
            ]
        }
        
        response = self.ecs.register_task_definition(**task_def)
        task_def_arn = response['taskDefinition']['taskDefinitionArn']
        print(f"✅ Registered task definition: {task_def_arn}")
        
        return task_def_arn
    
    def create_security_group(self):
        """Create security group for Fargate tasks"""
        print("\n🔒 Step 9: Creating Security Group...")
        
        # Get default VPC
        vpcs = self.ec2.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true']}])
        vpc_id = vpcs['Vpcs'][0]['VpcId']
        
        # Create security group
        try:
            response = self.ec2.create_security_group(
                GroupName=f'{self.project_name}-sg',
                Description='Security group for Max Training Agent',
                VpcId=vpc_id
            )
            sg_id = response['GroupId']
            
            # Allow inbound on port 8080
            self.ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 8080,
                        'ToPort': 8080,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }
                ]
            )
            print(f"✅ Created security group: {sg_id}")
        except self.ec2.exceptions.ClientError as e:
            if 'InvalidGroup.Duplicate' in str(e):
                # Get existing security group
                response = self.ec2.describe_security_groups(
                    Filters=[
                        {'Name': 'group-name', 'Values': [f'{self.project_name}-sg']},
                        {'Name': 'vpc-id', 'Values': [vpc_id]}
                    ]
                )
                sg_id = response['SecurityGroups'][0]['GroupId']
                print(f"✅ Security group already exists: {sg_id}")
            else:
                raise
        
        return sg_id, vpc_id
    
    def create_fargate_service(self, task_def_arn, sg_id, vpc_id):
        """Create Fargate service"""
        print("\n🚀 Step 10: Creating Fargate Service...")
        
        # Get subnets
        subnets = self.ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
        subnet_ids = [subnet['SubnetId'] for subnet in subnets['Subnets']]
        
        # Delete existing service if it exists
        try:
            self.ecs.delete_service(
                cluster=self.cluster_name,
                service=self.service_name,
                force=True
            )
            print("🗑️  Deleted existing service, waiting for cleanup...")
            
            # Wait for service to fully drain (up to 5 minutes)
            max_wait = 300  # 5 minutes
            wait_interval = 10
            elapsed = 0
            
            while elapsed < max_wait:
                try:
                    response = self.ecs.describe_services(
                        cluster=self.cluster_name,
                        services=[self.service_name]
                    )
                    
                    if not response['services'] or response['services'][0]['status'] == 'INACTIVE':
                        print("✅ Service fully drained")
                        break
                    
                    status = response['services'][0]['status']
                    print(f"   ⏳ Service status: {status}, waiting... ({elapsed}s/{max_wait}s)")
                    time.sleep(wait_interval)
                    elapsed += wait_interval
                except:
                    # Service not found, it's fully deleted
                    print("✅ Service fully drained")
                    break
            
            # Extra buffer time
            time.sleep(5)
        except:
            pass
        
        # Create service
        response = self.ecs.create_service(
            cluster=self.cluster_name,
            serviceName=self.service_name,
            taskDefinition=task_def_arn,
            desiredCount=1,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': subnet_ids,
                    'securityGroups': [sg_id],
                    'assignPublicIp': 'ENABLED'
                }
            }
        )
        
        service_arn = response['service']['serviceArn']
        print(f"✅ Created Fargate service: {service_arn}")
        
        # Wait for service to stabilize
        print("⏳ Waiting for service to start... (this may take 2-3 minutes)")
        waiter = self.ecs.get_waiter('services_stable')
        waiter.wait(
            cluster=self.cluster_name,
            services=[self.service_name],
            WaiterConfig={'Delay': 15, 'MaxAttempts': 20}
        )
        print("✅ Service is running!")
        
        return service_arn
    
    def get_task_public_ip(self):
        """Get public IP of running task"""
        print("\n🔍 Step 11: Getting Task Information...")
        
        # Get task ARN
        tasks = self.ecs.list_tasks(
            cluster=self.cluster_name,
            serviceName=self.service_name
        )
        
        if not tasks['taskArns']:
            print("⚠️  No tasks running yet")
            return None
        
        task_arn = tasks['taskArns'][0]
        
        # Get task details
        task_details = self.ecs.describe_tasks(
            cluster=self.cluster_name,
            tasks=[task_arn]
        )
        
        task = task_details['tasks'][0]
        
        # Get ENI ID
        eni_id = None
        for attachment in task['attachments']:
            for detail in attachment['details']:
                if detail['name'] == 'networkInterfaceId':
                    eni_id = detail['value']
                    break
        
        if not eni_id:
            print("⚠️  Could not find network interface")
            return None
        
        # Get public IP
        eni = self.ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
        public_ip = eni['NetworkInterfaces'][0].get('Association', {}).get('PublicIp')
        
        return public_ip, task_arn
    
    def display_deployment_info(self, repo_uri, task_def_arn, service_arn, public_ip, task_arn):
        """Display deployment information"""
        print("\n" + "=" * 80)
        print("✅ DEPLOYMENT COMPLETE!")
        print("=" * 80)
        print("\n📋 DEPLOYMENT INFORMATION:")
        print("-" * 80)
        print(f"🏷️  Project Name:        {self.project_name}")
        print(f"📍 Region:              {self.region}")
        print(f"🔑 Account ID:          {self.account_id}")
        print(f"🎯 ECS Cluster:         {self.cluster_name}")
        print(f"🚀 Service Name:        {self.service_name}")
        print("-" * 80)
        print("\n📦 CONTAINER INFORMATION:")
        print("-" * 80)
        print(f"🐳 ECR Repository:      {repo_uri}")
        print(f"📝 Task Definition:     {task_def_arn}")
        print(f"🔧 Service ARN:         {service_arn}")
        print(f"📋 Task ARN:            {task_arn}")
        print("-" * 80)
        print("\n🌐 ACCESS INFORMATION:")
        print("-" * 80)
        if public_ip:
            print(f"🌍 Public IP:           {public_ip}")
            print(f"🔗 Agent URL:           http://{public_ip}:8080")
            print(f"❤️  Health Check:        http://{public_ip}:8080/health")
        else:
            print("⚠️  Public IP not available yet - check ECS console")
        print("-" * 80)
        print("\n📊 MONITORING:")
        print("-" * 80)
        print(f"📋 CloudWatch Logs:     {self.log_group}")
        print(f"🔗 Logs URL:            https://console.aws.amazon.com/cloudwatch/home?region={self.region}#logsV2:log-groups/log-group/{self.log_group.replace('/', '$252F')}")
        print(f"🔗 ECS Console:         https://console.aws.amazon.com/ecs/v2/clusters/{self.cluster_name}/services/{self.service_name}")
        print("-" * 80)
        print("\n🧪 TESTING:")
        print("-" * 80)
        if public_ip:
            print(f"# Test health endpoint:")
            print(f"curl http://{public_ip}:8080/health")
            print(f"\n# Test agent:")
            print(f'curl -X POST http://{public_ip}:8080/invoke -H "Content-Type: application/json" -d \'{{"prompt": "What training services do you offer?", "customer_id": "cust_test"}}\'')
        print("=" * 80)
    
    def deploy(self):
        """Main deployment orchestration"""
        try:
            # Step 1: Create ECR repository
            repo_uri = self.create_ecr_repository()
            
            # Step 2: Create IAM roles
            execution_role_arn, task_role_arn = self.create_iam_roles()
            
            # Step 3: Create CodeBuild project
            project_name = self.create_codebuild_project(repo_uri)
            
            # Step 4: Upload source code to S3
            bucket_name, s3_key = self.upload_source_to_s3()
            
            # Step 5: Build and push Docker image using CodeBuild
            self.build_and_push_image(project_name, bucket_name, s3_key)
            
            # Step 6: Create log group
            self.create_log_group()
            
            # Step 7: Create ECS cluster
            self.create_ecs_cluster()
            
            # Step 8: Register task definition
            task_def_arn = self.register_task_definition(repo_uri, execution_role_arn, task_role_arn)
            
            # Step 9: Create security group
            sg_id, vpc_id = self.create_security_group()
            
            # Step 10: Create Fargate service
            service_arn = self.create_fargate_service(task_def_arn, sg_id, vpc_id)
            
            # Step 11: Get task information
            result = self.get_task_public_ip()
            if result:
                public_ip, task_arn = result
            else:
                public_ip, task_arn = None, None
            
            # Display deployment information
            self.display_deployment_info(repo_uri, task_def_arn, service_arn, public_ip, task_arn)
            
            return True
            
        except Exception as e:
            print(f"\n❌ Deployment failed: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == "__main__":
    # Fix encoding for Windows PowerShell
    import sys
    import io
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    # Region will be loaded from config.conf or environment
    deployer = FargateDeployer()
    success = deployer.deploy()
    sys.exit(0 if success else 1)
