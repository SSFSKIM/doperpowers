#!/usr/bin/env bash
# The devcloud image (Design §2): everything every host has, and never a
# credential, a boot descriptor, a ~/.claude checkout or a sminos enrollment.
# Run as root on Ubuntu 24.04 (x86_64 or arm64), from a devcloud checkout:
#
#   DEVCLOUD_USER=<user> DEVCLOUD_UID=<uid> DEVCLOUD_HOME=<home> devcloud/image/setup.sh
#
# The three inputs are the person's Mac account (the profile's build.env):
# the same home path lets a session started on a Mac resume on a host. A VM
# builder runs this and snapshots; image/Dockerfile runs it as its last step,
# after image/packages.sh's parts as layers of their own.
set -euo pipefail

: "${DEVCLOUD_USER:?set DEVCLOUD_USER, from the profile build.env}"
: "${DEVCLOUD_UID:?set DEVCLOUD_UID}"
: "${DEVCLOUD_HOME:?set DEVCLOUD_HOME}"
[[ "$DEVCLOUD_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || { echo "DEVCLOUD_USER is not a user name" >&2; exit 1; }
[[ "$DEVCLOUD_UID" =~ ^[0-9]+$ && "$DEVCLOUD_UID" -gt 0 ]] || { echo "DEVCLOUD_UID is not a uid above 0" >&2; exit 1; }
[[ "$DEVCLOUD_HOME" == /* ]] || { echo "DEVCLOUD_HOME is not an absolute path" >&2; exit 1; }
[[ "$(id -u)" == 0 ]] || { echo "run as root" >&2; exit 1; }
# An existing account of that name must be the one the inputs describe: one a
# base made otherwise (GCE's guest agent makes the project's ssh-keys users
# before cloud-init) would leave the host's paths and owners wrong.
if existing="$(getent passwd "$DEVCLOUD_USER")"; then
  IFS=: read -r _ _ have_uid _ _ have_home _ <<<"$existing"
  if [[ "$have_uid" != "$DEVCLOUD_UID" || "$have_home" != "$DEVCLOUD_HOME" ]]; then
    echo "user $DEVCLOUD_USER exists with uid $have_uid and home $have_home; this image needs uid $DEVCLOUD_UID and home $DEVCLOUD_HOME" >&2
    exit 1
  fi
fi

plugin="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The packages (image/packages.sh): image/Dockerfile runs them as layers of
# their own and says so; everywhere else they are this run's first step.
[[ "${DEVCLOUD_PACKAGES:-}" == installed ]] || bash "$plugin/image/packages.sh"

# The user: the Mac's name, uid and home, zsh as the login shell. Ubuntu's
# image ships an `ubuntu` user at uid 1000, which gives way when it is in the
# way — never on a machine being adopted (DEVCLOUD_ADOPTING=1), whose accounts
# are the person's.
if getent passwd "$DEVCLOUD_UID" >/dev/null && [[ "$(getent passwd "$DEVCLOUD_UID" | cut -d: -f1)" != "$DEVCLOUD_USER" ]]; then
  taken="$(getent passwd "$DEVCLOUD_UID" | cut -d: -f1)"
  [[ "$taken" == ubuntu && "${DEVCLOUD_ADOPTING:-}" != 1 ]] || { echo "uid $DEVCLOUD_UID is taken by $taken" >&2; exit 1; }
  userdel -r ubuntu 2>/dev/null || userdel ubuntu
fi
if ! getent passwd "$DEVCLOUD_USER" >/dev/null; then
  getent group "$DEVCLOUD_USER" >/dev/null || \
    if getent group "$DEVCLOUD_UID" >/dev/null; then groupadd "$DEVCLOUD_USER"; else groupadd -g "$DEVCLOUD_UID" "$DEVCLOUD_USER"; fi
  install -d -m 0755 "$(dirname "$DEVCLOUD_HOME")"
  useradd --uid "$DEVCLOUD_UID" --gid "$DEVCLOUD_USER" --home-dir "$DEVCLOUD_HOME" --create-home \
    --shell /usr/bin/zsh "$DEVCLOUD_USER"
fi
chsh -s /usr/bin/zsh "$DEVCLOUD_USER"
# Passwordless sudo, as cloud images give their default user: a project's
# devenv/setup.sh installs system packages. A drop-in, checked before it lands.
sudoers="$(mktemp)"
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$DEVCLOUD_USER" > "$sudoers"
chmod 0440 "$sudoers"
visudo -cf "$sudoers" >/dev/null
install -m 0440 -o root -g root "$sudoers" /etc/sudoers.d/devcloud-user
rm -f "$sudoers"
visudo -c >/dev/null

# Claude Code, the native installer, as the user; on every PATH through a link.
# Its own temporary directory, removed after: the installer leaves a socket behind.
scratch="$(runuser -u "$DEVCLOUD_USER" -- mktemp -d)"
runuser -u "$DEVCLOUD_USER" -- env HOME="$DEVCLOUD_HOME" TMPDIR="$scratch" \
  bash -c 'curl -fsSL https://claude.ai/install.sh | bash'
rm -rf "$scratch"
ln -sfn "$DEVCLOUD_HOME/.local/bin/claude" /usr/local/bin/claude

# devcloud itself: the boot program, the service runner, the CLI.
install -d -m 0755 /usr/local/lib/devcloud /etc/devcloud
cp -R "$plugin/boot/." /usr/local/lib/devcloud/
find /usr/local/lib/devcloud -name __pycache__ -prune -exec rm -rf {} +
chmod -R go-w /usr/local/lib/devcloud
for program in devcloud devcloud-boot devcloud-services; do
  ln -sfn "/usr/local/lib/devcloud/$program" "/usr/local/bin/$program"
done
printf 'DEVCLOUD_USER=%s\nDEVCLOUD_UID=%s\nDEVCLOUD_HOME=%s\n' "$DEVCLOUD_USER" "$DEVCLOUD_UID" "$DEVCLOUD_HOME" \
  > /etc/devcloud/image.env

# /etc/devcloud/env reaches every shell of the user's: every zsh reads
# /etc/zsh/zshenv (login, interactive, and the `zsh -c` of Claude Code's Bash
# tool); bash login shells read /etc/profile.d. Root's shells skip it: the
# file may put the user's directories on PATH.
marker='# devcloud: the host environment'
if ! grep -qF "$marker" /etc/zsh/zshenv 2>/dev/null; then
  cat >> /etc/zsh/zshenv <<'ZSH'

# devcloud: the host environment (/etc/devcloud/env), for every zsh but root's.
if [[ $EUID -ne 0 ]]; then
  [[ ":$PATH:" == *":$HOME/.local/bin:"* ]] || export PATH="$HOME/.local/bin:$PATH"
  if [[ -r /etc/devcloud/env ]]; then set -a; . /etc/devcloud/env; set +a; fi
fi
ZSH
fi
cat > /etc/profile.d/devcloud.sh <<'SH'
# devcloud: the host environment (/etc/devcloud/env), for every login shell but root's.
if [ "$(id -u)" -ne 0 ]; then
  case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH"; export PATH ;; esac
  if [ -r /etc/devcloud/env ]; then set -a; . /etc/devcloud/env; set +a; fi
fi
SH

# Where systemd is PID 1 (a VM or microVM), the boot program runs at every boot
# that has a descriptor: an image's first boot, before the driver has installed
# one, skips it rather than recording a failed boot. Where cloud-init runs, after
# its config stage (users, keys, files written); not after its final stage,
# which Ubuntu orders after multi-user.target, a cycle for a unit that target
# wants. cloud-init's runcmd may start this unit itself (--no-block).
cat > /etc/systemd/system/devcloud-boot.service <<'UNIT'
[Unit]
Description=devcloud: make this machine a devcloud host (boot steps 1-12)
Wants=network-online.target
After=network-online.target cloud-init.service cloud-config.service
ConditionPathExists=/etc/devcloud/boot.env

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/devcloud-boot
# 3: the host is made and only step 12 (projects) failed; the services, ordered
# after this unit, start, and `devcloud status` names the failure.
SuccessExitStatus=3
TimeoutStartSec=45min

[Install]
WantedBy=multi-user.target
UNIT
if command -v systemctl >/dev/null; then systemctl enable devcloud-boot.service; fi

# A GCE spot VM's fast departure when the provider reclaims it (the driver's
# §4.2): its stop, at shutdown, departs only when the metadata server says the
# VM is being reclaimed. Shipped disabled; the boot enables it on a spot VM
# (DEVCLOUD_SPOT=1). Ordered after the network, the tailnet and the user
# manager, so it stops before they do.
cat > /etc/systemd/system/devcloud-spot.service <<'UNIT'
[Unit]
Description=devcloud: depart fast when the provider reclaims this spot VM
Wants=network-online.target
After=network-online.target tailscaled.service user.slice systemd-user-sessions.service devcloud-boot.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/true
ExecStop=/usr/local/bin/devcloud depart --preempted
TimeoutStopSec=28

[Install]
WantedBy=multi-user.target
UNIT

rm -rf /root/.cache "$DEVCLOUD_HOME/.cache"

# What the image never carries (acceptance 6): no descriptor, no credential, no checkout, no enrollment.
for path in /etc/devcloud/boot.env /var/lib/devcloud "$DEVCLOUD_HOME/.claude/.git" \
            "$DEVCLOUD_HOME/.config/claude-secrets" "$DEVCLOUD_HOME/.config/gcloud" "$DEVCLOUD_HOME/.config/gh" \
            "$DEVCLOUD_HOME/.claude/sminos/daemon"; do
  if [[ -e "$path" ]]; then echo "the image must not hold $path" >&2; exit 1; fi
done
