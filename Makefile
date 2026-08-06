# Hermes control plane + web UI — containerized service management.
#
# Everything runs in a container: the FastAPI control plane, the REST/WebSocket API,
# and the web UI (the built SPA is baked into the image). The server binds loopback
# on this host.
#
# Data lives in ~/.hermes, bind-mounted in as /hermes-home, so the container and the
# `hermes` CLI share ONE home. This used to be a podman named volume, which put the
# data under ~/.local/share/containers/storage/volumes/ instead -- a second, invisible
# home. The CLI wrote to ~/.hermes and the UI read the volume, so the board showed
# "No active run" while runs sat in the database.
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
#   make deploy           # rebuild code+SPA and restart (the everyday path)
#   make up PORT=44105    # run on a different loopback port
#   make down             # stop
#
# NETWORK vs OFFLINE targets
# --------------------------
# Targets marked [NET] reach the internet (pull a base image / install packages).
# An AI agent's traffic is filtered in this environment and those pulls FAIL for
# it, so [NET] targets are meant to be run BY A HUMAN (they use `with-proxy`).
# Everything else is offline and safe for an agent to run.
#
#   [NET] image       — full rebuild; pulls the python base image. RUN THIS YOURSELF.
#   [NET] deps        — install/refresh web dependencies (npm ci). RUN THIS YOURSELF.
#   [NET] browser     — install Playwright + Chromium for UI tests. RUN THIS YOURSELF.
#         image-fast  — code+SPA onto the existing image (no pull) — agent-safe
#         deploy      — image-fast + restart — agent-safe, the everyday path
#         ui-test     — run the real-browser UI tests (needs `make browser` once)
#         shots       — write screenshots to web/screenshots/ — agent-safe
#
# Use `make image` (human) after changing Python/npm DEPENDENCIES; `make deploy`
# handles every code/UI change because the package is installed editable.

PORT   ?= 44102
IMAGE  ?= hermes-control-plane:latest
NAME   ?= hermes-control-plane
# The host's Hermes home, shared with the CLI. Honour HERMES_HOME if it is set,
# so the container follows the same override everything else does.
HOME_DIR ?= $(if $(HERMES_HOME),$(HERMES_HOME),$(HOME)/.hermes)
# Local adapter directory, mounted separately from the home. It usually sits inside
# the home, but it does not have to -- and when it is a symlink to a checkout
# elsewhere, the container cannot follow it out of the home's bind mount. Mounting
# the resolved path and setting HERMES_LOCAL_DIR inside makes discovery work either way.
LOCAL_DIR ?= $(if $(HERMES_LOCAL_DIR),$(HERMES_LOCAL_DIR),$(HOME_DIR)/local)
# Mounted read-only, and only when it exists -- an absent directory must not become an
# empty one that podman creates on the host.
LOCAL_MOUNT := $(if $(wildcard $(LOCAL_DIR)/.),-e HERMES_LOCAL_DIR=/hermes-local -v $(LOCAL_DIR):/hermes-local:ro,)
PROXY  ?= with-proxy
URL    := http://127.0.0.1:$(PORT)

.PHONY: help web deps browser ui-test shots image image-fast deploy up down restart status health logs shell url token clean

help: ## list targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-11s\033[0m %s\n",$$1,$$2}'

web: ## build the SPA (web/dist) baked into the image (offline)
	cd web && npm run build

deps: ## [NET — RUN THIS YOURSELF] install/refresh web dependencies
	cd web && $(PROXY) npm ci

browser: ## [NET — RUN THIS YOURSELF] install Playwright + Chromium for real-browser UI tests
	cd web && $(PROXY) npm install --save-dev --no-audit --no-fund @playwright/test
	cd web && $(PROXY) npx playwright install chromium
	@echo
	@echo "Chromium installed. Layout behaviour that jsdom cannot see (scrolling,"
	@echo "overscroll, spacing) is now testable: 'make ui-test' and 'make shots'."

ui-test: ## run the real-browser UI tests (needs `make browser` once; offline)
	cd web && npx playwright test

shots: ## screenshot every view into web/screenshots/ (needs `make browser`; offline)
	cd web && npx playwright test --grep @shot

image: web ## [NET — RUN THIS YOURSELF] full image rebuild (pulls the python base image)
	$(PROXY) podman build --network=host -f fleet/Dockerfile.control-plane -t $(IMAGE) .

image-fast: web ## rebuild code+SPA onto the existing image (offline; deps unchanged)
	podman build --network=host -f fleet/Dockerfile.control-plane.fast -t $(IMAGE) .

deploy: image-fast restart ## rebuild code+SPA and restart (offline; the everyday path)
	@$(MAKE) --no-print-directory health

up: ## start the containerized web UI on $(PORT) (offline; needs the image to exist)
	@podman image exists $(IMAGE) || { \
	  echo "No $(IMAGE) image yet. That first build pulls a base image, so run it yourself:"; \
	  echo "    make image"; \
	  exit 1; }
	-@podman rm -f $(NAME) >/dev/null 2>&1 || true
	@mkdir -p $(HOME_DIR)
	podman run -d --network=host --name $(NAME) \
	  -e HERMES_BIND=127.0.0.1 \
	  -v $(HOME_DIR):/hermes-home \
	  $(LOCAL_MOUNT) \
	  $(IMAGE) hermes serve --api --port $(PORT)
	@echo "Hermes web UI (containerized) -> $(URL)  (loopback; token auto-injected)"
	@echo "Serving $(HOME_DIR) — the same home the CLI writes to."
	@$(if $(LOCAL_MOUNT),echo "Local adapters from $(LOCAL_DIR) (read-only).",echo "No local adapter directory at $(LOCAL_DIR) — none loaded.")

down: ## stop + remove the container (the home directory is untouched)
	-podman rm -f $(NAME)

restart: ## restart the container (reuses the current image)
	@$(MAKE) down
	@$(MAKE) up

status: ## container state + health
	@podman ps --filter name=$(NAME) --format "table {{.Names}}\t{{.Status}}\t{{.Command}}" || true
	@$(MAKE) --no-print-directory health

health: ## check the API health endpoint (waits briefly for a starting server)
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
	  if curl -fsS -m 5 $(URL)/api/health 2>/dev/null; then \
	    echo "  [OK $(URL)]"; exit 0; \
	  fi; \
	  sleep 1; \
	done; \
	echo "not responding on $(PORT)"; exit 1

logs: ## follow container logs
	podman logs -f $(NAME)

shell: ## open a shell in the running container
	podman exec -it $(NAME) /bin/bash

url: ## print the web UI URL
	@echo "$(URL)"

token: ## where the API token lives / how to rotate it
	@echo "Token: $(HOME_DIR)/api_token (auto-injected on loopback)."
	@echo "Rotate: podman exec $(NAME) hermes serve --api --rotate-token && $(MAKE) restart"

clean: down ## stop + remove the image ($(HOME_DIR) is left alone)
	-podman rmi $(IMAGE)
