# Sandbox image for JavaScript and TypeScript agents. The install step writes the
# project's dependencies into a volume mounted over its node_modules; the run step
# mounts that volume read-only and can reach only the proxy.
FROM node:22-bookworm-slim

# pnpm beside the npm and yarn the base image ships, so any lockfile installs (pnpm 10 also
# reads a pnpm-workspace.yaml that only carries settings, which pnpm 9 refuses); tsx so a
# TypeScript entry point runs without the project having to depend on a runner.
RUN npm install --global --no-fund --no-audit pnpm@10 tsx@4 \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin agent \
    && mkdir -p /work && chown agent:agent /work
WORKDIR /work
USER agent
ENV HOME=/tmp \
    NODE_ENV=production \
    npm_config_update_notifier=false \
    npm_config_fund=false \
    npm_config_audit=false \
    npm_config_manage_package_manager_versions=false \
    CI=1
# The last one keeps pnpm from fetching the exact version a project's packageManager field names,
# which it cannot write into the sandbox home; the pnpm installed here reads any v9 lockfile.
