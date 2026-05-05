.PHONY: help deploy deploy-app deploy-pkg deploy-meta status logs logs-build logs-follow restart hardware-gpu hardware-cpu

SPACE ?= vlm-run/mm-ctx
MSG   ?= ui polish

EXCLUDES := \
	--exclude "__pycache__/**" --exclude "**/__pycache__/**" \
	--exclude "data/**" --exclude "**/data/**" \
	--exclude "*.pyc" --exclude "Makefile" --exclude ".gitignore" \
	--exclude "spaces_app.py" --exclude "Dockerfile" --exclude "README.md"

help: ## List targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "  Override the target Space with SPACE=<owner/name>"
	@echo "  Override the commit message with MSG=\"...\""
	@echo "  e.g. make deploy SPACE=username/mm-ctx MSG=\"hotfix\""

deploy: deploy-meta deploy-app deploy-pkg ## Push Dockerfile + README + spaces_app.py + gradio_app/ to $(SPACE)

deploy-meta: ## Push Dockerfile + README.md to the Space root
	hf upload --repo-type space $(SPACE) Dockerfile Dockerfile \
		--commit-message "$(MSG) [Dockerfile]"
	hf upload --repo-type space $(SPACE) README.md README.md \
		--commit-message "$(MSG) [README]"

deploy-app: ## Push spaces_app.py to $(SPACE) as the Space root app.py
	hf upload --repo-type space $(SPACE) spaces_app.py app.py \
		--commit-message "$(MSG) [app.py]"

deploy-pkg: ## Push gradio_app/ contents to $(SPACE):gradio_app/
	hf upload --repo-type space $(SPACE) . gradio_app \
		$(EXCLUDES) \
		--commit-message "$(MSG) [gradio_app]"

status: ## Show stage, runtime sha, head sha, hardware
	@hf spaces info $(SPACE) | python3 -c "import json,sys; d=json.load(sys.stdin); r=d['runtime']; raw=r['raw']; print(f\"stage    : {r['stage']}\nrun sha  : {raw.get('sha','?')[:8]}\nhead sha : {d['sha'][:8]}\nhardware : {raw.get('hardware',{}).get('current')} (req {raw.get('hardware',{}).get('requested')})\nprivate  : {d.get('private')}\nhost     : {d['host']}\")"

logs: ## Tail run logs (use -- '-n 200' for more lines)
	hf spaces logs $(SPACE) -n 80

logs-build: ## Tail container build logs
	hf spaces logs $(SPACE) --build -n 80

logs-follow: ## Stream run logs
	hf spaces logs $(SPACE) -f

restart: ## Force the Space to reboot (factory rebuild)
	hf spaces dev-mode $(SPACE) --stop || true
	@echo "Triggering rebuild via empty commit…"
	hf upload --repo-type space $(SPACE) . gradio_app \
		$(EXCLUDES) \
		--commit-message "restart"

hardware-gpu: ## Switch $(SPACE) to zero-a10g (HF Pro)
	@python3 -c "from huggingface_hub import HfApi; r=HfApi().request_space_hardware('$(SPACE)', hardware='zero-a10g'); print('requested:', r.requested_hardware, 'stage:', r.stage)"

hardware-cpu: ## Switch $(SPACE) to cpu-basic (free)
	@python3 -c "from huggingface_hub import HfApi; r=HfApi().request_space_hardware('$(SPACE)', hardware='cpu-basic'); print('requested:', r.requested_hardware, 'stage:', r.stage)"
