# Package Name: ewccli
# License: GPL-3.0-or-later
# Copyright (c) 2025 EUMETSAT, ECMWF for European Weather Cloud
# See the LICENSE file for more details

# This retrieves the container image from:
# https://hub.docker.com/_/python
FROM docker.io/python:3.12-slim

# Enable apt packages list
RUN apt update

# Create ewcuser for automation
RUN set -ex \
    # Create a non-root user
    && addgroup --system --gid 1001 ewccli \
    && adduser --system --uid 1001 --home /home/ewccli -gid 1001 ewccli

# Setup and create app dir
ENV APP_DIR=/usr/local/opt/ewccli-automation
RUN mkdir -p $APP_DIR

# Set working directory
WORKDIR $APP_DIR

# Copy your local package repository into the container
# Assuming your package is in ./my_package relative to the Containerfile
COPY ./dist/*.whl $APP_DIR/

# Upgrade pip and install the local package
RUN python -m pip install --upgrade pip

RUN pip install --no-cache-dir $APP_DIR/*.whl

# Execute everything below as user 'ewccli'
USER 1001

# Execute the run.sh
ENTRYPOINT ["ewc"]
