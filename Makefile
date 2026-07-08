#   dev Mac:  RELEASE_TAG=2026-07-09-Jatin make push-prod
#   prod box: set RELEASE_TAG in .env, then: make pull-prod
-include .env

RELEASE_TAG  ?= latest
ECR_REGISTRY ?= 851725268918.dkr.ecr.ap-south-1.amazonaws.com
AWS_REGION   ?= ap-south-1
AWS_PROFILE  ?= dev

IMG_API = $(ECR_REGISTRY)/zs/nubra-ai:nubra-beacon-api-$(RELEASE_TAG)
IMG_WEB = $(ECR_REGISTRY)/zs/nubra-ai:nubra-beacon-webapp-$(RELEASE_TAG)

S=api

.PHONY: ecr-login push-prod pull-prod up down logs migrate postgres_connect

ecr-login:
	aws ecr get-login-password --region $(AWS_REGION) --profile $(AWS_PROFILE) \
        | docker login --username AWS --password-stdin $(ECR_REGISTRY)

# Build both images for the prod architecture on this Mac and push to ECR.
push-prod: ecr-login
	docker buildx build --platform linux/amd64 -f Dockerfile.api -t $(IMG_API) --push .
	docker buildx build --platform linux/amd64 \
	--build-arg NEXT_PUBLIC_API_BASE=http://api:8400/api/v1 \
	-t $(IMG_WEB) --push webapp
	@echo "pushed $(RELEASE_TAG) — set RELEASE_TAG=$(RELEASE_TAG) in prod .env, then: make pull-prod"

# On the prod machine: pull the tag from .env, roll the stack. The `migrate` service applies migrations on the way up and api gates on it completing.
pull-prod: ecr-login
	docker compose app pull api webapp

up:
	docker compose up -d ${S}

down:
	docker compose down

logs:
	docker compose logs -f ${S}

# Run migrations on their own via the dedicated one-shot service (works whether or not the api container is up).
migrate:
	docker compose run --rm migrate

postgres_connect:
	psql "$(DB_URL)"

