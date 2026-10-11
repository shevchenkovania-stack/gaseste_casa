#!/usr/bin/env bash
# SSH hardening for the box that holds BOT_TOKEN and (soon) payment data.
#
#   scp deploy/harden_ssh.sh root@<IP>:/tmp/
#   ssh root@<IP> "sed -i 's/\r$//' /tmp/harden_ssh.sh && bash /tmp/harden_ssh.sh"
#
# Why it exists: `sshd -T` on this server reports PermitRootLogin=yes + PasswordAuthentication=yes on
# port 22, i.e. the machine openly accepts "root + password" from the internet, and that account can
# read every secret of a money-handling bot. The default action here is fail2ban: it bans brute
# forcers and **cannot lock the owner out** (our own address goes to ignoreip). Killing password login
# for root is the better fix but it is the one command in this project that can lock a human out of
# his own server, so it is deliberately opt-in and requires the key path to be proven first:
#
#   bash /tmp/harden_ssh.sh --disable-root-password
#
# Idempotent: re-running changes nothing and bans nobody.
set -e

echo "=== current effective sshd config ==="
sshd -T 2>/dev/null | grep -Ei '^(port|permitrootlogin|passwordauthentication|pubkeyauthentication|kbdinteractiveauthentication) '

ME=$(echo "${SSH_CLIENT:-}" | awk '{print $1}')
echo "=== our address (never banned): ${ME:-unknown} ==="

echo "=== fail2ban ==="
if ! command -v fail2ban-client >/dev/null; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y fail2ban >/dev/null
  echo "установлен"
else
  echo "уже стоит: $(fail2ban-client --version 2>/dev/null | tail -1)"
fi

# jail.local stays untouched: our drop-in is separate, so an OS update of the package cannot erase it
cat > /etc/fail2ban/jail.d/imobiliare.conf <<EOF
[sshd]
enabled  = true
port     = 22
backend  = systemd
maxretry = 5
findtime = 10m
bantime  = 1h
# a ban that cuts off the only admin is worse than no ban at all
ignoreip = 127.0.0.1/8 ::1 ${ME}
EOF

systemctl enable fail2ban >/dev/null 2>&1
systemctl restart fail2ban
sleep 2
systemctl is-active fail2ban
fail2ban-client status sshd

echo "=== sshd still healthy (reload would be the dangerous step; there is none here) ==="
systemctl is-active ssh

if [ "$1" = "--disable-root-password" ]; then
  echo "=== opt-in: root only by key ==="
  # Proof before permission: the ONLY way this can lock us out is if key login from this address does
  # not actually work, so require sshd's own log to say so within this session window. Checking with
  # `ssh root@$ME` would be wrong (that address is the client, not an ssh server), and `ssh localhost`
  # would test the server's own keys, which we never use. BatchMode on the client side already means
  # "no password was typed" - the journal is the server-side half of that proof.
  if [ -z "$ME" ]; then
    echo "SSH_CLIENT пуст — скрипт запущен не по ssh, доказательности входа по ключу нет. Не трогаем."
    exit 1
  fi
  if ! journalctl -u ssh -u sshd --no-pager --since "-30 min" 2>/dev/null \
       | grep -q "Accepted publickey for root from ${ME}"; then
    echo "В журнале sshd нет 'Accepted publickey for root from ${ME}' — текущий вход не по ключу."
    echo "Отключать пароль нельзя: останемся без доступа. Сначала добавь ключ (ssh-copy-id) и повтори."
    exit 1
  fi
  echo "журнал sshd подтверждает: вход по ключу с ${ME} был — отключаю пароль для root"
  cat > /etc/ssh/sshd_config.d/99-imobiliare.conf <<'EOF'
# deploy/harden_ssh.sh: root gets in by key only. Password auth stays for any other user.
PermitRootLogin prohibit-password
EOF
  if ! sshd -t; then
    echo "sshd -t не прошёл — конфиг НЕ применён, файл убран, sshd не перезагружен"
    rm -f /etc/ssh/sshd_config.d/99-imobiliare.conf
    exit 1
  fi
  systemctl reload ssh        # reload (not restart): live sessions are never dropped
  sleep 2
  systemctl is-active ssh
  sshd -T 2>/dev/null | grep -Ei '^permitrootlogin '
  echo "ОТКАТ (пока эта сессия жива): rm /etc/ssh/sshd_config.d/99-imobiliare.conf && systemctl reload ssh"
  echo "ОБЯЗАТЕЛЬНО: не закрывая это окно, открой НОВОЕ с машины с ключом и зайди ещё раз."
  echo "Если не пускает — откатывай командой выше; плюс у VPS есть консоль провайдера."
else
  echo "=== пароль root всё ещё принимается (шаг человека, один флаг) ==="
  echo "bash /tmp/harden_ssh.sh --disable-root-password"
  echo "После этого вход в сервер будет возможен ТОЛЬКО с машины, где лежит ключ (см. ACCESS.md)."
fi

echo "OK: fail2ban стоит и следит за sshd, бан 1h после 5 неудач за 10 мин, наш адрес не банится"
