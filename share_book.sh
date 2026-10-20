#!/bin/bash
set -euo pipefail

# Validate positional arguments
if [ "$#" -lt 3 ]; then
    echo "Usage: $0 BOOK_URL BUCKET_NAME EXPIRES_IN_SECONDS" >&2
    exit 1
fi

URL="$1"
BUCKET="$2"
EXPIRES="$3"
FILE_NAME="$(basename "$URL")"

# Download the book into books/, keeping the file name from the URL
mkdir -p books
curl -fL -o "books/$FILE_NAME" "$URL"

# Create the bucket unless it already exists
if ! aws s3 ls "s3://$BUCKET" > /dev/null 2>&1; then
    aws s3 mb "s3://$BUCKET"
fi

# Upload the book; the bucket and book stay private
aws s3 cp "books/$FILE_NAME" "s3://$BUCKET/$FILE_NAME" \
    --content-type "text/plain; charset=utf-8"

# Presign a URL with the requested expiration and print it
aws s3 presign "s3://$BUCKET/$FILE_NAME" --expires-in "$EXPIRES"

