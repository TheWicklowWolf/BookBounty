FROM python:3.12-alpine

# Set build arguments
ARG RELEASE_VERSION
ENV RELEASE_VERSION=${RELEASE_VERSION}
ENV BB_PORT=${BB_PORT:-5000}

# Create User
ARG UID=1000
ARG GID=1000
RUN addgroup -g $GID general_user && \
    adduser -D -u $UID -G general_user -s /bin/sh general_user

RUN apk --no-cache --no-interactive update && apk --no-cache --no-interactive upgrade

# Create directories and set permissions
COPY . /bookbounty
WORKDIR /bookbounty
RUN mkdir -p /bookbounty/downloads
RUN chown -R $UID:$GID /bookbounty
RUN chmod -R 777 /bookbounty/downloads

# Install requirements and run code as general_user
RUN pip install --root-user-action=ignore --no-cache-dir --upgrade pip && \
    pip install --root-user-action=ignore --no-cache-dir -r requirements.txt
EXPOSE ${BB_PORT}
USER general_user
CMD exec gunicorn src.BookBounty:app -b 0.0.0.0:${BB_PORT} -c gunicorn_config.py