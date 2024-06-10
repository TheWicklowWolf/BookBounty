FROM python:3.12-alpine
# Create User
ARG UID=1000
ARG GID=1000
RUN addgroup -g $GID general_user && \
    adduser -D -u $UID -G general_user -s /bin/sh general_user
# Create directories and set permissions
COPY . /bookbounty
WORKDIR /bookbounty
RUN mkdir -p /bookbounty/downloads
RUN chown -R $UID:$GID /bookbounty
RUN chmod -R 777 /bookbounty/downloads
# Install requirements and run code as general_user
RUN pip install --no-cache-dir -r requirements.txt
EXPOSE 5000
USER general_user
CMD ["gunicorn","src.BookBounty:app", "-c", "gunicorn_config.py"]