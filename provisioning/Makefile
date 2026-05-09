SHELL := /bin/sh

ENV_FILE := .env
ENV_EXAMPLE := .env.example
TAILSCALE_TEMPLATE := tailscale-config/serve.template.json
TAILSCALE_CONFIG := tailscale-config/serve.json
BOOTSTRAP_IMAGE := bootstrap-test.qcow2
DOCKER_COMPOSE := docker compose -f docker-compose.yml --env-file $(ENV_FILE)

.PHONY: init start restart test vm clean stop reset

init:
	@if [ ! -f "$(ENV_FILE)" ]; then \
		cp "$(ENV_EXAMPLE)" "$(ENV_FILE)"; \
		printf 'Created %s from %s\n' "$(ENV_FILE)" "$(ENV_EXAMPLE)"; \
	else \
		printf '%s already exists; leaving it unchanged\n' "$(ENV_FILE)"; \
	fi

$(TAILSCALE_CONFIG): $(TAILSCALE_TEMPLATE) $(ENV_FILE)
	@TAILNET_NAME=$$(awk -F= '/^TAILNET_NAME=/{print substr($$0, index($$0, "=") + 1); exit}' "$(ENV_FILE)"); \
	if [ -z "$$TAILNET_NAME" ]; then \
		printf 'TAILNET_NAME is not set in %s\n' "$(ENV_FILE)" >&2; \
		exit 1; \
	fi; \
	awk -v tailnet_name="$$TAILNET_NAME" '{ gsub(/\$$\{TAILNET_NAME\}/, tailnet_name); print }' "$(TAILSCALE_TEMPLATE)" > "$(TAILSCALE_CONFIG)"; \
	printf 'Rendered %s\n' "$(TAILSCALE_CONFIG)"

start: init $(TAILSCALE_CONFIG)
	@$(DOCKER_COMPOSE) up -d

# ts-secret-api and secret-api share a network namespace; both must restart together
restart: init $(TAILSCALE_CONFIG)
	@$(DOCKER_COMPOSE) restart ts-secret-api secret-api

test:
	@uv run pytest

vm:
	@if [ -z "$(IMAGE_PATH)" ]; then \
		printf 'IMAGE_PATH is required, for example: make vm IMAGE_PATH=/path/to/ubuntu-cloudimg.qcow2\n' >&2; \
		exit 1; \
	fi; \
	VM_NAME="$${VM_NAME:-bootstrap-test}"; \
	CREATE_OUTPUT="$$(uv run python scripts/create_node.py --hostname "$$VM_NAME")"; \
	printf '%s\n' "$$CREATE_OUTPUT"; \
	SEED_TOKEN="$$(printf '%s\n' "$$CREATE_OUTPUT" | awk -F= '/^seed_token=/{print substr($$0, index($$0, "=") + 1); exit}')"; \
	if [ -z "$$SEED_TOKEN" ]; then \
		printf 'Failed to extract seed_token from create_node.py output\n' >&2; \
		exit 1; \
	fi; \
	IMAGE_PATH="$(IMAGE_PATH)" VM_NAME="$$VM_NAME" SEED_TOKEN="$$SEED_TOKEN" ./scripts/qemu_test.sh

clean:
	@rm -f "$(TAILSCALE_CONFIG)" "build/bootstrap-test.qcow2"

stop:
	@$(DOCKER_COMPOSE) down

reset: stop clean start