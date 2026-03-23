#!/bin/bash
USER=ubuntu
sudo chown -R ${USER}:${USER} /home/${USER}/.config 2>/dev/null || true
uv pip install --no-cache-dir -e /opt/netbox-wdm
exec "$@"
