---
title: Docker Compose
description: Learn how to deploy CiteGuild using Docker Compose.
keywords: CiteGuild, deployment, render, self-hosting
author: LVTD LLC
---

Deploy CiteGuild on your own server using Docker Compose.

## What you'll learn

- Set up CiteGuild with Docker Compose
- Configure environment variables
- Access your deployed application
- Troubleshoot common deployment issues

## Overview

Docker Compose provides a streamlined way to deploy CiteGuild on your server. This method handles all services (database, Redis, backend, and workers) with a single command.

This approach works best if you have a VPS or dedicated server where you can run Docker.

The production compose stack uses PostgreSQL 18, Redis 8.6.3, and application images built with Python 3.14.5 and Node.js 24.15.0 LTS.

The backend and workers services run the same application image. The compose file sets `APP_PROCESS_TYPE=server` for the backend and `APP_PROCESS_TYPE=worker` for workers.

## Prerequisites

Before starting, make sure you have:

- A server with Docker and Docker Compose installed
- SSH access to your server
- Basic familiarity with command line
- OpenRouter API key for optional AI features

## Setup steps

### 1. Create deployment directory

SSH into your server and create a folder for CiteGuild:

```bash
mkdir citeguild-deployment
cd citeguild-deployment
```

### 2. Download and configure environment file

Download the example environment file from the CiteGuild repository:

```bash
wget https://github.com/LVTD-LLC/citeguild/raw/main/.env.example -O .env
```

Or if you prefer curl:

```bash
curl -o .env https://github.com/LVTD-LLC/citeguild/raw/main/.env.example
```

Now edit the `.env` file to add your credentials:

```bash
nano .env
```

You need to configure several environment variables for CiteGuild to work properly. See the [Environment Variables](/docs/deployment/environment-variables/) guide for complete details on all available options.

At minimum, update these required values:

- App image if pulling from a registry (`APP_IMAGE`, for example `ghcr.io/<owner>/<repository>:latest`)
- OpenRouter API key (`OPENROUTER_API_KEY`) if optional AI features are enabled
- Database password (POSTGRES_PASSWORD)
- Redis password (REDIS_PASSWORD)
- Django secret key (SECRET_KEY)
- Allowed hosts (ALLOWED_HOSTS)
- Debug mode (DEBUG - set to False for production)

The `.env.example` file includes all available configuration options with explanations. Update any additional settings you need.

Save the file (in nano: Ctrl+X, then Y, then Enter).

### 3. Download docker-compose file

Download the production docker-compose configuration from the CiteGuild repository:

```bash
wget https://github.com/LVTD-LLC/citeguild/raw/main/docker-compose-prod.yml -O docker-compose-prod.yml
```

Or if you prefer curl:

```bash
curl -o docker-compose-prod.yml https://github.com/LVTD-LLC/citeguild/raw/main/docker-compose-prod.yml
```
You can use the file as-is, or customize it if needed.

### 4. Start the application

Run this command to start all services:

```bash
docker-compose -f docker-compose-prod.yml -p "citeguild" up --detach --remove-orphans || true
```

Docker will:
- Download the necessary images
- Create the database and Redis containers
- Start the backend and worker services
- Run database migrations automatically

This takes 2-5 minutes on first deployment.

### 5. Verify deployment

Check that all services are running:

```bash
docker-compose ps
```

You should see four containers running: `db`, `redis`, `backend`, and `workers`.

Check the logs to ensure no errors:

```bash
docker-compose logs backend
```

## Expose your application

The backend runs on port 8000. You need to expose it to the internet.

### Option 1: Direct port access

If your server allows it, access CiteGuild at:

```
http://your-server-ip:8000
```

This works for testing but isn't recommended for production.

### Option 2: Nginx reverse proxy (recommended)

Install Nginx on your server:

```bash
sudo apt update
sudo apt install nginx
```

Create an Nginx configuration:

```bash
sudo nano /etc/nginx/sites-available/citeguild
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/citeguild /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

Now access CiteGuild at `http://yourdomain.com`.

### Option 3: Add SSL with Certbot

Secure your site with HTTPS:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Follow the prompts. Certbot automatically configures SSL and sets up auto-renewal.
