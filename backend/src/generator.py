import boto3
import os
import urllib.parse

s3 = boto3.client('s3')
BUCKET_NAME = os.environ['STAGING_BUCKET']

def handler(event, context):
    # Get the object from the event
    # S3 Event structure: Records[0].s3.object.key
    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    
    # Extract request_id from key "uploads/{request_id}/source.zip"
    # key parts: ["uploads", "{request_id}", "source.zip"]
    parts = key.split('/')
    if len(parts) < 3:
        print("Invalid key format")
        return
        
    request_id = parts[1]
    
    # Generate presigned GET URL for the source zip (valid for 2 hours)
    source_zip_url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': BUCKET_NAME, 'Key': key},
        ExpiresIn=7200
    )
    
    # Construct the CloudFormation Template
    # We escape the python code for the inline Lambda using double braces for format() if needed, 
    # but here we are just using f-string for the URL.
    
    cft_content = f"""AWSTemplateFormatVersion: '2010-09-09'
Description: Prodify Static Site - Hosted on S3 + CloudFront
Resources:
  WebsiteBucket:
    Type: AWS::S3::Bucket
    Properties:
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  CloudFrontOriginAccessControl:
    Type: AWS::CloudFront::OriginAccessControl
    Properties:
      OriginAccessControlConfig:
        Name: !Sub "${{AWS::StackName}}-OAC"
        OriginAccessControlOriginType: s3
        SigningBehavior: always
        SigningProtocol: sigv4

  WebsiteBucketPolicy:
    Type: AWS::S3::BucketPolicy
    Properties:
      Bucket: !Ref WebsiteBucket
      PolicyDocument:
        Version: '2008-10-17'
        Id: PolicyForCloudFrontPrivateContent
        Statement:
          - Sid: AllowCloudFrontServicePrincipal
            Effect: Allow
            Principal:
              Service: cloudfront.amazonaws.com
            Action: s3:GetObject
            Resource: !Sub "${{WebsiteBucket.Arn}}/*"
            Condition:
              StringEquals:
                "AWS:SourceArn": !Sub "arn:aws:cloudfront::${{AWS::AccountId}}:distribution/${{CloudFrontDistribution}}"

  CloudFrontDistribution:
    Type: AWS::CloudFront::Distribution
    Properties:
      DistributionConfig:
        Enabled: true
        DefaultRootObject: index.html
        Origins:
          - Id: S3Origin
            DomainName: !GetAtt WebsiteBucket.RegionalDomainName
            OriginAccessControlId: !Ref CloudFrontOriginAccessControl
            S3OriginConfig:
              OriginAccessIdentity: ''
        DefaultCacheBehavior:
          TargetOriginId: S3Origin
          ViewerProtocolPolicy: redirect-to-https
          CachePolicyId: 658327ea-f89d-4fab-a63d-7e88639e58f6
          OriginRequestPolicyId: 88a5eaf4-2fd4-4709-b370-b4c650ea3fcf
        CustomErrorResponses:
          - ErrorCode: 403
            ResponseCode: 200
            ResponsePagePath: /index.html
          - ErrorCode: 404
            ResponseCode: 200
            ResponsePagePath: /index.html

  DeployerRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: DeployerPolicy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action:
                  - s3:PutObject
                  - s3:DeleteObject
                  - s3:ListBucket
                Resource:
                  - !GetAtt WebsiteBucket.Arn
                  - !Sub ${{WebsiteBucket.Arn}}/*
              - Effect: Allow
                Action:
                  - logs:CreateLogGroup
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource: arn:aws:logs:*:*:*

  ContentDeployer:
    Type: AWS::Lambda::Function
    Properties:
      PackageType: Image
      Role: !GetAtt DeployerRole.Arn
      Timeout: 900
      MemorySize: 3008
      EphemeralStorage:
        Size: 2048
      Architectures:
        - arm64
      Code:
        ImageUri: 532931254745.dkr.ecr.us-east-1.amazonaws.com/prodify-content-deployer@sha256:654a4b4b1e6a5d12c60534d30600a52b407ed046ba0a4f757d5e67ff8246d17a

  DeploymentTrigger:
    Type: Custom::ContentDeployer
    Properties:
      ServiceToken: !GetAtt ContentDeployer.Arn
      SourceZipUrl: "{source_zip_url}"
      BucketName: !Ref WebsiteBucket

Outputs:
  CloudFrontURL:
    Value: !Sub "https://${{CloudFrontDistribution.DomainName}}"
    Description: CloudFront URL for your website
  S3BucketName:
    Value: !Ref WebsiteBucket
    Description: S3 bucket name
"""

    # Upload the generated template
    output_key = f"generated/{request_id}/template.yaml"
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=output_key,
        Body=cft_content,
        ContentType='application/x-yaml'
    )
    
    print(f"Generated template at {output_key}")
