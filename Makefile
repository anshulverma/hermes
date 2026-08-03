# Hermes control plane + web UI — containerized service management.
#
# Everything runs in a container: the FastAPI control plane, the REST/WebSocket API,
# and the web UI (the built SPA is baked into the image). Data (queue.db + api_token)
# persists in the `hermes-home` podman volume. The server binds loopback on this host.
#
# Networking: this host's rootless podman has no bridge networking (netavark/nftables),
# so the container uses --network=host and the server binds 127.0.0.1:$(PORT) directly.
# (fleet/docker-compose.control-plane.yml is the portable equivalent for hosts that do
# have bridge networking / run behind a proxy.)
#
# Quick start:
#   make up               # start the UI (builds the image if needed) -> http://127.0.0.1:44102
#   make status           # container state + health
#   make logs             # follow logs
#   make image            # (re)build the image after code/UI changes
#   make image restart    # rebuild + restart
#   make up PORT=44105    # run on a different loopback port
#   make down             # stop

PORT   ?= 44102
IMAGE  ?= hermes-control-plane:latest
NAME   ?= hermes-control-plane
VOLUME ?= hermes-home
PROXY  ?= with-proxy
URL    := http://127.0.0.1:$(PORT)

.PHONY: help web image image-fast up down restart status health logs shell url token clean

help: ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-9s\033[0m %s\n",$$1,$$2}'

web: ## build the SPA (web/dist) that gets baked into the image
	cd web && $(PROXY) npm run build

image: web ## (re)build the control-plane image (SPA baked in)
	$(PROXY) podman build --network=host -f fleet/Dockerfile.control-plane -t $(IMAGE) .

image-fast: web ## rebuild code+SPA onto the existing image (seconds, no base pull; deps unchanged)
	$(PROXY) podman build --network=host -f fleet/Dockerfile.control-plane.fast -t $(IMAGE) .

up: ## start the containerized web UI on $(PORT) (builds the image if missing)
	@podman image exists $(IMAGE) || $(MAKE) image
	-@podman rm -f $(NAME) >/dev/null 2>&1 || true
	podman run -d --network=host --name $(NAME) \
	  -e HERMES_BIND=127.0.0.1 \
	  -v $(VOLUME):/hermes-home \
	  $(IMAGE) hermes serve --api --port $(PORT)
	@echo "Hermes web UI (containerized) -> $(URL)  (loopback; token auto-injected)"

down: ## stop + remove the container (data volume preserved)
	-podman rm -f $(NAME)

restart: ## restart the container (reuses the current image)
	@$(MAKE) down
	@$(MAKE) up

status: ## container state + health
	@podman ps --filter name=$(NAME) --format "table {{.Names}}\t{{.Status}}\t{{.Command}}" || true
	@$(MAKE) --no-print-directory health

health: ## check the API health endpoint
	@curl -fsS -m 5 $(URL)/api/health && echo "  [OK $(URL)]" || echo "not responding on $(PORT)"

logs: ## follow container logs
	podman logs -f $(NAME)

shell: ## open a shell in the running container
	podman exec -it $(NAME) /bin/bash

url: ## print the web UI URL
	@echo "$(URL)"

token: ## where the API token lives / how to rotate it
	@echo "Token: in the '$(VOLUME)' volume at /hermes-home/api_token (auto-injected on loopback)."
	@echo "Rotate: podman exec $(NAME) hermes serve --api --rotate-token && $(MAKE) restart"

clean: down ## stop + remove the image (data volume preserved; remove it with: podman volume rm $(VOLUME))
	-podman rmi $(IMAGE)
