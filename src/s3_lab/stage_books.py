#!/usr/bin/env python3

import json
import logging
import os
import sys
import time

import boto3
import requests
from botocore.exceptions import ClientError

# Logger setup
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)
# One S3 client shared by all functions (uses ~/.aws/credentials)
s3 = boto3.client("s3", region_name="us-east-1")

def parse_args():
    """Read the command line arguments"""
    if len(sys.argv) < 4:
        log.error("Usage: stage_books.py BOOK_LIST INDEX_HTML BUCKET_NAME")
        sys.exit(1)
    return sys.argv[1], sys.argv[2], sys.argv[3]


def download_books(list_file, dest_dir):
    """Download every book listed in list_file into dest_dir."""
    os.makedirs(dest_dir, exist_ok=True)
    paths = []

    try:
        with open(list_file) as f:
            urls = [line.strip() for line in f if line.strip()]
    except OSError as e:
        log.error(f"Cannot read {list_file}: {e}")
        return paths

    for url in urls:
        # Save under the last part of the URL
        path = os.path.join(dest_dir, url.rsplit("/", 1)[-1])
 
        # Skip books we already have so reruns are fast
        if os.path.exists(path):
            log.info(f"Already downloaded, skipping: {path}")
            paths.append(path)
            continue
 
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()  # raise an error for 404 etc.
            with open(path, "wb") as out:
                out.write(response.content)
            log.info(f"Downloaded {url} -> {path}")
            paths.append(path)
        except (requests.RequestException, OSError) as e:
            log.error(f"Error downloading {url}: {e}")

        time.sleep(1)

    return paths

def create_bucket(bucket_name):
    """Create the bucket unless it already exists"""
    # Check whether the bucket already exists and is accessible
    try:
        s3.head_bucket(Bucket=bucket_name)
        log.info(f"Bucket {bucket} already exists")
        return True
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code not in ("404", "NoSuchBucket"):
            log.error(f"Cannot access bucket {bucket_name}: {e}")
            return False
 
    # Bucket does not exist yet: create it (us-east-1 needs no LocationConstraint)
    try:
        s3.create_bucket(Bucket=bucket_name)
        log.info(f"Created bucket {bucket_name}")
        return True
    except ClientError as e:
        log.error(f"Error creating bucket {bucket_name}: {e}")
        return False

def make_public(bucket_name):
    """Turn off Block Public Access and allow anyone to read objects"""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket_name}/*",
            }
        ],
    }
 
    try:
        # Must happen first, otherwise the policy is rejected
        s3.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": False,
                "IgnorePublicAcls": False,
                "BlockPublicPolicy": False,
                "RestrictPublicBuckets": False,
            },
        )
        log.info(f"Block Public Access turned off for {bucket_name}")
 
        s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
        log.info(f"Public read policy attached to {bucket_name}")
        return True
    except ClientError as e:
        log.error(f"Error making bucket {bucket_name} public: {e}")
        return False


def upload_files(bucket_name, file_paths):
    """Upload each file to the top level of the bucket as text/plain."""
    count = 0
    for path in file_paths:
        key = os.path.basename(path)  
        try:
            s3.upload_file(
                path,
                bucket_name,
                key,
                ExtraArgs={"ContentType": "text/plain; charset=utf-8"},
            )
            log.info(f"Uploaded {path} -> s3://{bucket_name}/{key}")
            count += 1
        except (ClientError, OSError, boto3.exceptions.S3UploadFailedError) as e:
            log.error(f"Error uploading {path}: {e}")
    return count
 
 
def upload_index(bucket_name, index_path):
    """Upload the index page as index.html with a web page content type"""
    try:
        s3.upload_file(
            index_path,
            bucket_name,
            "index.html",
            ExtraArgs={"ContentType": "text/html"},
        )
        log.info(f"Uploaded {index_path} -> s3://{bucket_name}/index.html")
        return True
    except FileNotFoundError:
        log.error(f"File not found: {index_path}")
        return False
    except (ClientError, boto3.exceptions.S3UploadFailedError) as e:
        log.error(f"Error uploading {index_path}: {e}")
        return False

def main():
    """Run all steps: download, create bucket, make public, upload."""
    list_file, index_path, bucket_name = parse_args()
    books = download_books(list_file, "books")
    if not books:
        log.error("No books were downloaded")
        sys.exit(1)

    if not create_bucket(bucket_name):
        log.error("Could not create the bucket")
        sys.exit(1)

    if not make_public(bucket_name):
        log.error("Could not make the bucket public")
        sys.exit(1)

    uploaded = upload_files(bucket_name, books)
    index_ok = upload_index(bucket_name, index_path)

    if index_ok and uploaded == len(books):
        log.info(f"Success: uploaded {uploaded} books and index.html")
    else:
        log.error(f"Finished with problems: {uploaded}/{len(books)} books uploaded, "
                  f"index uploaded: {index_ok}")
    log.info(f"Public URL: https://{bucket_name}.s3.amazonaws.com/index.html")


if __name__ == "__main__":
    main()

