import os
import uuid
import boto3
from fastapi import HTTPException
from botocore.exceptions import NoCredentialsError, PartialCredentialsError, ClientError
from typing import Optional
import io

class S3Service:
    def __init__(self):
        self._s3_client = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of S3 client"""
        if self._initialized:
            return
            
        self.bucket_name = os.getenv("S3_BUCKET_NAME")
        self.aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.aws_region = os.getenv("AWS_REGION")
        self.cloudfront_domain = os.getenv("CLOUDFRONT_DOMAIN", "d3srmxrzq4dz1v.cloudfront.net")
        
        if not all([self.bucket_name, self.aws_access_key_id, self.aws_secret_access_key, self.aws_region]):
            raise ValueError("S3 credentials not properly configured")
        
        self._s3_client = boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.aws_region
        )
        self._initialized = True
    
    @property
    def s3_client(self):
        self._ensure_initialized()
        return self._s3_client

    def upload_file(self, file_data: bytes, content_type: str, folder: str, filename: Optional[str] = None) -> str:
        """
        Upload file data to S3 and return the public URL
        
        Args:
            file_data: The file content as bytes
            content_type: MIME type of the file
            folder: S3 folder/prefix (e.g., 'images', 'audio', 'videos')
            filename: Optional filename. If not provided, generates UUID
        
        Returns:
            Public URL of the uploaded file
        """
        if not filename:
            file_extension = self._get_extension_from_content_type(content_type)
            filename = f"{uuid.uuid4()}{file_extension}"
        
        key = f"{folder}/{filename}"
        
        # Ensure S3 client is initialized
        self._ensure_initialized()
        
        try:
            # Upload file to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=file_data,
                ContentType=content_type,
                ACL='public-read'  # Make file publicly accessible
            )
            
            # Return CloudFront URL if available, otherwise S3 URL
            if self.cloudfront_domain:
                return f"https://{self.cloudfront_domain}/{key}"
            else:
                return f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{key}"
                
        except NoCredentialsError:
            raise HTTPException(status_code=500, detail="AWS credentials not found")
        except PartialCredentialsError:
            raise HTTPException(status_code=500, detail="Incomplete AWS credentials")
        except ClientError as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload to S3: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Unexpected error during S3 upload: {str(e)}")

    def upload_from_url(self, source_url: str, folder: str, filename: Optional[str] = None) -> str:
        """
        Download file from URL and upload to S3
        
        Args:
            source_url: URL to download file from
            folder: S3 folder/prefix
            filename: Optional filename
        
        Returns:
            Public URL of the uploaded file
        """
        import httpx
        
        try:
            # Download file from URL
            with httpx.Client() as client:
                response = client.get(source_url)
                response.raise_for_status()
                
                content_type = response.headers.get('content-type', 'application/octet-stream')
                file_data = response.content
                
                return self.upload_file(file_data, content_type, folder, filename)
                
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"Failed to download file from {source_url}: {str(e)}")

    def _get_extension_from_content_type(self, content_type: str) -> str:
        """Get file extension from MIME type"""
        content_type_map = {
            'image/jpeg': '.jpg',
            'image/jpg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'audio/mpeg': '.mp3',
            'audio/wav': '.wav',
            'audio/mp4': '.m4a',
            'video/mp4': '.mp4',
            'video/quicktime': '.mov',
            'video/x-msvideo': '.avi',
            'application/octet-stream': '.bin'
        }
        return content_type_map.get(content_type.lower(), '.bin')

# Global instance
s3_service = S3Service()