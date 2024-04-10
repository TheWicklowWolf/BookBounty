# BookBounty

![Build Status](https://github.com/TheWicklowWolf/BookBounty/actions/workflows/main.yml/badge.svg)
![Docker Pulls](https://img.shields.io/docker/pulls/thewicklowwolf/bookbounty.svg)

![bookbounty](https://github.com/TheWicklowWolf/BookBounty/assets/111055425/394d8830-fa7b-462e-9de8-aa91d0e1b971)


Web GUI for finding missing Readarr books.


## Run using docker-compose

```yaml
services:
  bookbounty:
    image: thewicklowwolf/bookbounty:latest
    container_name: bookbounty
    environment:
      - readarr_address=http://192.168.1.2:8787
      - readarr_api_key=0123456789
      - libgen_address=http://libgen.is
    ports:
      - 5000:5000
    volumes:
      - /path/to/downloads:/bookbounty/downloads
    restart: unless-stopped

```
---

![BookBounty](https://github.com/TheWicklowWolf/BookBounty/assets/111055425/c965dedb-dc04-4dce-9932-4f13a0821cec)


---


![BookBounty_Dark](https://github.com/TheWicklowWolf/BookBounty/assets/111055425/dfb5ec88-57c7-4651-b0c5-7f61c4556c4e)


---

https://hub.docker.com/r/thewicklowwolf/bookbounty
