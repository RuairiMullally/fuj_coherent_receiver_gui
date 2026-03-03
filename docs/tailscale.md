# Tailscale Remote Access

Access the FIM24725 UI from any device on a Tailscale network —
no VPN configuration, no port forwarding, no public internet exposure.

---

## No rebuild needed

Both services bind to `0.0.0.0`, so they already listen on the Pi's Tailscale
interface (`tailscale0`) alongside its LAN interface. As soon as the Tailscale
ACL permits traffic on port 8050, the UI is reachable.

Find the Pi's Tailscale IP:

```bash
tailscale ip -4
```

Then open `http://<that-ip>:8050` from any device on the same tailnet.

---

## Personal tailnet (testing — you are the admin)

The simplest path if you want to try remote access without touching the org
Tailscale account:

1. Create a personal Tailscale account at [tailscale.com](https://tailscale.com)
   (free tier supports up to 3 users and 100 devices).
2. On the Pi, log in to your personal account (this replaces the current org login):
   ```bash
   sudo tailscale login
   ```
   Follow the link to authenticate. The Pi will appear in your personal tailnet.
3. Do the same on each client device (laptop, etc.).
4. Personal tailnets use the **default ACL**, which allows all traffic between all
   member devices — no further configuration needed.
5. Open `http://<pi-tailscale-ip>:8050`.

To return the Pi to the org tailnet later:
```bash
sudo tailscale login --reauth
```
and authenticate with the org account.

---

## Org tailnet (hand this snippet to your admin)

If the Pi is already on the org tailnet, ask your Tailscale admin to add the
following rule. It allows all authenticated tailnet members to reach the UI:

```hujson
// Allow all tailnet members to reach the FIM24725 UI
{
  "acls": [
    {
      "action": "accept",
      "src":    ["autogroup:member"],
      "dst":    ["<pi-tailscale-ip>:8050"]
    }
  ]
}
```

**To also allow direct API / Swagger UI access** (port 8000), extend `dst`:

```hujson
"dst": ["<pi-tailscale-ip>:8050", "<pi-tailscale-ip>:8000"]
```

**Tags for finer control**: if your admin has configured device tags (e.g.
`tag:lab-member`), replace `autogroup:member` with that tag to restrict access
to specific devices rather than all org members.

---

## Security

- Tailscale is a **WireGuard-based mesh VPN** — all traffic between devices is
  end-to-end encrypted and never traverses the public internet.
- The `0.0.0.0` bind address in `docker-compose.yml` is required so the
  `network_mode: host` container can use all of the Pi's network interfaces,
  including `tailscale0`. It does **not** expose the port to the internet — that
  is controlled by the Pi's firewall, which is separate from the bind address.

### Optional: lock ports to Tailscale only (ufw)

If you want to prevent LAN access and allow only Tailscale clients:

```bash
# Allow port 8050 only on the Tailscale interface
sudo ufw allow in on tailscale0 to any port 8050
sudo ufw deny 8050

# Same for the API if desired
sudo ufw allow in on tailscale0 to any port 8000
sudo ufw deny 8000

sudo ufw enable
```

Verify:
```bash
sudo ufw status
```

---

## References

- [Tailscale ACL documentation](https://tailscale.com/kb/1018/acls)
- [Tailscale subnet routers](https://tailscale.com/kb/1019/subnets) (not needed here — direct device access)
- [Pi deployment guide](pi_setup.md)
