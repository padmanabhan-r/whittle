# EC2 deployment

The `CI and deploy` workflow runs backend tests and frontend lint/build checks on
GitHub-hosted runners for pull requests and pushes to `main`. After a successful
push to `main`, its deploy job runs on the self-hosted runner installed on the
Whittle EC2 instance. The runner makes an outbound connection to GitHub; the
instance does not need to allow inbound SSH from GitHub.

Complete the one-time setup before pushing this workflow to `main`; otherwise,
the deploy job will remain queued waiting for the EC2 runner.

## One-time setup

1. In the repository, open **Settings → Secrets and variables → Actions →
   Variables** and add `WHITTLE_API_URL` with the public API URL, for example
   `http://35.171.208.95:8787`. This is public configuration, not a secret.
2. On the EC2 instance, sign in as `ubuntu` and open the repository's **Settings
   → Actions → Runners → New self-hosted runner** page. Select Linux x64 and run
   the displayed download and configuration commands in a new directory such as
   `/home/ubuntu/actions-runner`. Add the label `whittle-ec2` during
   configuration if you have runner-management access; otherwise the workflow
   also accepts the runner's default `self-hosted`, `Linux`, and `X64` labels.
   The registration token is temporary; do not commit or share it.
3. Ensure the EC2 account that cloned the private repository is authenticated
   with GitHub CLI and configure Git to use it for fetches:

   ```bash
   gh auth status
   gh auth setup-git
   ```

4. Install and start the runner as a service so it reconnects after an instance
   reboot:

   ```bash
   sudo ./svc.sh install ubuntu
   sudo ./svc.sh start
   sudo ./svc.sh status
   ```

5. Confirm that the runner appears **Online** in the repository's Actions
   runner settings. Keep inbound SSH limited to your own address; the workflow
   does not need AWS credentials or an SSH private key.

The instance needs the existing deployment checkout at
`/home/ubuntu/whittle-main`, with its `.env.local` and Docker access configured.
Do not add `.env.local` or provider keys to GitHub Actions variables or secrets.

## What a deployment does

After checks pass on a push to `main`, the EC2 job fast-forwards the deployment
checkout, syncs backend dependencies, installs frontend dependencies, builds
the UI with `WHITTLE_API_URL`, and restarts the `whittle-main` tmux session in
production-preview mode. It verifies the local UI, API docs, and proxy health
endpoints. Existing ignored job data and `.env.local` stay in place. If the
checkout has local tracked changes or cannot fast-forward, deployment stops
instead of overwriting them.

Pull-request workflows run only on GitHub-hosted workers. The EC2 runner must
remain restricted to trusted `main`-branch deployment code; do not add
pull-request jobs to it. When EC2 is stopped, the runner is offline and a
deployment job waits for it to come back online, subject to GitHub's queue
timeout. The running app itself must also be started after an instance reboot
unless a separate boot service is configured.
