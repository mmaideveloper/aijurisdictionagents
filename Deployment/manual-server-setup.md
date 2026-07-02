# Manual Server Setup For Codex SSH Access

This runbook describes how to prepare a new Ubuntu server and configure SSH access for Codex from the local Windows workstation.

For package installation, GitHub checkout, Docker/PostgreSQL preparation, API smoke deployment, and laws connector preparation, continue with `Deployment/self-managed-server-deployment.md` after SSH access is verified.

Current server target:

- Host alias: `jurisdigta-server`
- Hostname/IP: `192.168.1.25`
- Server user: `jurisdigta-admin`
- Client key path: `C:\Users\maton\.ssh\id_ed25519`
- Public key USB filename: `jurisdigta-server-id_ed25519.pub`

## Compliance And Security Baseline

- Keep private SSH keys only on the client workstation. Never copy `id_ed25519` to the server, USB drive, repository, chat, or shared storage.
- Copy only the public key, `id_ed25519.pub`, to the server.
- Use a named non-root administrator account such as `jurisdigta-admin`; avoid routine SSH login as `root`.
- Use least privilege for future deployment automation and keep human approval for legal-risk production changes.
- Do not commit private keys, host keys, passwords, personal access tokens, certificates, or server inventory containing sensitive access details.
- Treat SSH logs and deployment logs as operational security records. Avoid logging personal data or legal-risk user content.

These controls support GDPR privacy-by-design, data minimization, traceability, and human oversight expectations for systems that may process legal-risk outputs.

## 1. Install Ubuntu Server

1. Download the Ubuntu Server LTS installer from the official Ubuntu website.
2. Install Ubuntu Server 26.04 LTS on the target machine.
3. During installation:
   - Set hostname to `jurisdigta-server`.
   - Create the administrator user `jurisdigta-admin`.
   - Use a strong local password for first-time console access.
   - Enable OpenSSH during installation when the installer offers it.
4. After first boot, sign in locally or through the server console.
5. Confirm network identity:

```bash
hostname
ip address
```

Expected hostname:

```text
jurisdigta-server
```

Expected LAN address for this setup:

```text
192.168.1.25
```

## 2. Install Or Enable OpenSSH Server

On the Ubuntu server:

```bash
sudo apt update
sudo apt install openssh-server
sudo systemctl enable --now ssh
sudo systemctl status ssh --no-pager
```

If UFW is active, allow SSH:

```bash
sudo ufw allow OpenSSH
sudo ufw status
```

If UFW is inactive, it is not blocking SSH.

Confirm SSH is listening:

```bash
ss -tlnp | grep ':22'
```

Expected output includes a listener on port `22`, for example:

```text
LISTEN 0 4096 0.0.0.0:22
LISTEN 0 4096 [::]:22
```

From the Windows workstation, confirm TCP access:

```powershell
Test-NetConnection -ComputerName 192.168.1.25 -Port 22
```

Expected result:

```text
TcpTestSucceeded : True
```

## 3. Create The SSH Key On The Codex Workstation

On the Windows workstation, create the SSH directory if needed:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.ssh"
```

Generate an Ed25519 key:

```powershell
ssh-keygen -t ed25519 -C "maton-jurisdigta-server" -f "$env:USERPROFILE\.ssh\id_ed25519"
```

For unattended local automation, an empty passphrase may be used if the workstation account and disk are appropriately protected. For stricter security, use a passphrase and load it through `ssh-agent`.

Verify the public key:

```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
```

Do not print or share the private key:

```text
C:\Users\maton\.ssh\id_ed25519
```

## 4. Copy The Public Key To USB

Insert the USB drive into the Windows workstation. If it appears as `E:`, copy the public key:

```powershell
Copy-Item -LiteralPath "$env:USERPROFILE\.ssh\id_ed25519.pub" -Destination "E:\jurisdigta-server-id_ed25519.pub" -Force
Get-ChildItem E:\jurisdigta-server-id_ed25519.pub
```

Only this public key file should be copied to the USB drive.

## 5. Mount The USB Drive On Ubuntu

Insert the USB drive into the Ubuntu server and identify the device:

```bash
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS
```

Look for the removable USB partition, for example:

```text
sdb
`-sdb1  vfat
```

Do not use the EFI partition mounted at `/boot/efi`.

Mount the USB partition:

```bash
sudo mkdir -p /mnt/usb
sudo umount /mnt/usb 2>/dev/null || true
sudo mount /dev/sdb1 /mnt/usb
ls -la /mnt/usb
```

Expected file:

```text
jurisdigta-server-id_ed25519.pub
```

If the file is not visible, check whether Ubuntu auto-mounted the USB under `/media`:

```bash
find /media /mnt -name 'jurisdigta-server-id_ed25519.pub' 2>/dev/null
```

## 6. Install The Public Key For The Server User

On the Ubuntu server:

```bash
sudo mkdir -p /home/jurisdigta-admin/.ssh
cat /mnt/usb/jurisdigta-server-id_ed25519.pub | sudo tee -a /home/jurisdigta-admin/.ssh/authorized_keys > /dev/null
sudo chown -R jurisdigta-admin:jurisdigta-admin /home/jurisdigta-admin/.ssh
sudo chmod 700 /home/jurisdigta-admin/.ssh
sudo chmod 600 /home/jurisdigta-admin/.ssh/authorized_keys
sudo tail -n 1 /home/jurisdigta-admin/.ssh/authorized_keys
```

Unmount the USB drive:

```bash
sudo umount /mnt/usb
```

## 7. Configure The Local SSH Alias

Create or update `C:\Users\maton\.ssh\config` on the Windows workstation:

```sshconfig
Host jurisdigta-server
    HostName 192.168.1.25
    User jurisdigta-admin
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

Accept the host key on first connection:

```powershell
ssh jurisdigta-server
```

When prompted, type:

```text
yes
```

Then verify non-interactive access:

```powershell
ssh -o BatchMode=yes jurisdigta-server "hostname && whoami"
```

Expected output:

```text
jurisdigta-server
jurisdigta-admin
```

This is the minimal runnable validation example for Codex server connectivity.

Next runbook:

```text
Deployment/self-managed-server-deployment.md
```

After the repository is cloned on the server, the repeatable package/deployment-root bootstrap is:

```bash
cd /srv/jurisdigta/app
bash Deployment/server/setup_jurisdigta_server.sh
```

## 8. Troubleshooting

If `Test-NetConnection` fails but ping works:

- Confirm `sudo systemctl status ssh --no-pager`.
- Confirm `ss -tlnp | grep ':22'`.
- Confirm no network or VLAN rule blocks traffic between the workstation and `192.168.1.25`.

If SSH says `Host key verification failed`:

- Run `ssh jurisdigta-server` manually once and accept the host key.
- If the server was reinstalled, remove the old key with:

```powershell
ssh-keygen -R 192.168.1.25
ssh-keygen -R jurisdigta-server
```

If SSH asks for a password after the public key was copied:

- Check the public key is one complete line in `/home/jurisdigta-admin/.ssh/authorized_keys`.
- Check ownership and permissions:

```bash
sudo chown -R jurisdigta-admin:jurisdigta-admin /home/jurisdigta-admin/.ssh
sudo chmod 700 /home/jurisdigta-admin/.ssh
sudo chmod 600 /home/jurisdigta-admin/.ssh/authorized_keys
```

If the USB mount shows no file:

- Re-check the partition with `lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINTS`.
- Mount the removable USB partition such as `/dev/sdb1`.
- Do not mount or write to `/boot/efi`.

## 9. Rollback

To remove Codex SSH access from the server:

1. Edit `/home/jurisdigta-admin/.ssh/authorized_keys`.
2. Remove the line ending with `maton-jurisdigta-server`.
3. Save the file.
4. Confirm access is removed:

```powershell
ssh -o BatchMode=yes jurisdigta-server "hostname"
```

Expected result after rollback is authentication failure.

To remove the local client configuration:

```powershell
Remove-Item "$env:USERPROFILE\.ssh\config"
```

Only remove the private key if it is not used for any other host:

```powershell
Remove-Item "$env:USERPROFILE\.ssh\id_ed25519"
Remove-Item "$env:USERPROFILE\.ssh\id_ed25519.pub"
```
