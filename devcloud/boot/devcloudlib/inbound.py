"""The inbound policy (Design §5): with `DEVCLOUD_INBOUND=tailnet`, once the
tailnet is up, inbound traffic is dropped but for loopback, the tailnet's
interface, established and related traffic, ICMP and ICMPv6 (IPv6 neighbor
discovery needs it), Tailscale's direct connections (UDP 41641) and DHCP
replies. Outbound is untouched. One nftables table devcloud owns, `inet
devcloud`, loaded now and, by `devcloud-inbound.service`, before the network
comes up at every later boot; the file deletes and redefines the table, so a
reload is idempotent and no rule devcloud did not write is touched. The
ruleset and unit are M1's, verified on a Hetzner VM across a reboot."""

import pathlib

from .proc import run as proc_run, write_file

NFT = pathlib.Path("/etc/devcloud/inbound.nft")
UNIT = "devcloud-inbound.service"
UNIT_DIR = pathlib.Path("/etc/systemd/system")
TABLE = "inet devcloud"
TAILSCALE_PORT = 41641


def ruleset():
    return f"""# Written by devcloud (boot step 4, Design §5): inbound only over the tailnet.
table {TABLE}
delete table {TABLE}
table {TABLE} {{
  chain input {{
    type filter hook input priority filter; policy drop;
    iif "lo" accept
    iifname "tailscale0" accept
    ct state established,related accept
    ct state invalid drop
    meta l4proto icmp accept
    meta l4proto ipv6-icmp accept
    udp dport {TAILSCALE_PORT} accept
    udp sport 67 udp dport 68 accept
    udp sport 547 udp dport 546 accept
  }}
}}
"""


def unit(nft_path=NFT):
    return f"""[Unit]
Description=devcloud: inbound only over the tailnet (Design §5)
DefaultDependencies=no
Before=network-pre.target
Wants=network-pre.target
After=local-fs.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f {nft_path}
ExecStop=/usr/sbin/nft delete table {TABLE}

[Install]
WantedBy=sysinit.target
"""


def apply(run=proc_run, nft_path=NFT, unit_dir=UNIT_DIR):
    """Writes the ruleset and its unit, enables the unit and loads the table
    now: a restart when either file changed, else a start (nothing when it
    runs already). Returns a status detail."""
    nft_path, unit_dir = pathlib.Path(nft_path), pathlib.Path(unit_dir)
    rules_changed = write_file(nft_path, ruleset(), mode=0o644, dir_mode=0o755)
    unit_changed = write_file(unit_dir / UNIT, unit(nft_path), mode=0o644, dir_mode=0o755)
    if unit_changed:
        run(["systemctl", "daemon-reload"], log="tailnet", timeout=60)
    run(["systemctl", "enable", UNIT], log="tailnet", timeout=60)
    run(["systemctl", "restart" if rules_changed or unit_changed else "start", UNIT], log="tailnet", timeout=60)
    return f"inbound closed but for the tailnet ({TABLE})"
