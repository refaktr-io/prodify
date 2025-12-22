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
      Handler: index.handler
      Role: !GetAtt DeployerRole.Arn
      Runtime: python3.9
      Timeout: 300
      Code:
        ZipFile: |
          import boto3
          import urllib.request
          import zipfile
          import io
          import json
          import mimetypes
          
          def send(event, context, responseStatus, responseData, physicalResourceId=None, noEcho=False):
              responseUrl = event['ResponseURL']
              responseBody = {{
                  'Status': responseStatus,
                  'Reason': 'See the details in CloudWatch Log Stream: ' + context.log_stream_name,
                  'PhysicalResourceId': physicalResourceId or context.log_stream_name,
                  'StackId': event['StackId'],
                  'RequestId': event['RequestId'],
                  'LogicalResourceId': event['LogicalResourceId'],
                  'NoEcho': noEcho,
                  'Data': responseData
              }}
              json_responseBody = json.dumps(responseBody)
              headers = {{
                  'content-type': '',
                  'content-length': str(len(json_responseBody))
              }}
              try:
                  req = urllib.request.Request(responseUrl, data=json_responseBody.encode('utf-8'), headers=headers, method='PUT')
                  with urllib.request.urlopen(req) as response:
                      print("Status code: " + response.reason)
              except Exception as e:
                  print("send(..) failed executing requests.put(..): " + str(e))

          def handler(event, context):
              try:
                  if event['RequestType'] == 'Delete':
                      send(event, context, 'SUCCESS', {{}})
                      return
                  
                  source_url = event['ResourceProperties']['SourceZipUrl']
                  bucket = event['ResourceProperties']['BucketName']
                  
                  print(f"Downloading from {{source_url}}")
                  with urllib.request.urlopen(source_url) as response:
                      zip_content = response.read()
                  
                  print("Unzipping and uploading...")
                  s3 = boto3.client('s3')
                  
                  # Detect if there's a root folder by checking all files
                  with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
                      all_files = z.namelist()
                      
                      # Check if all files are in a single root folder
                      root_folder = None
                      if all_files:
                          first_path = all_files[0]
                          if '/' in first_path:
                              potential_root = first_path.split('/')[0] + '/'
                              if all(f.startswith(potential_root) or f == potential_root[:-1] for f in all_files):
                                  root_folder = potential_root
                      
                      for filename in all_files:
                          # Skip macOS metadata files and directories
                          if filename.startswith('__MACOSX/') or filename.startswith('.') or '/__MACOSX/' in filename or '/.' in filename:
                              continue
                          if not filename.endswith('/'):
                              # Strip root folder if detected
                              upload_key = filename
                              if root_folder and filename.startswith(root_folder):
                                  upload_key = filename[len(root_folder):]
                              
                              # Skip if empty key after stripping
                              if not upload_key:
                                  continue
                              
                              content_type, _ = mimetypes.guess_type(filename)
                              if not content_type:
                                  content_type = 'application/octet-stream'
                              
                              s3.put_object(
                                  Bucket=bucket,
                                  Key=upload_key,
                                  Body=z.read(filename),
                                  ContentType=content_type
                              )
                  
                  send(event, context, 'SUCCESS', {{}})
              except Exception as e:
                  print(e)
                  send(event, context, 'FAILED', {{}})

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
