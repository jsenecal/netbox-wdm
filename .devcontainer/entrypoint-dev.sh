#!/bin/bash

USER=ubuntu

sudo chown -R ${USER}:${USER} /etc/netbox/scripts
sudo chown -R ${USER}:${USER} /home/${USER}/.config
sudo chown -R ${USER}:${USER} /home/${USER}/.claude
sudo chown ${USER}:${USER} /home/${USER}/.claude.json 2>/dev/null || true

# Reconfigure User id if set by user
if [ ! -z "${USER_UID}" ] && [ "${USER_UID}" != "`id -u ${USER}`" ] ; then
  echo -n "Update uid for user ${USER} with ${USER_UID}"
  usermod -u ${USER_UID} ${USER}
  echo "... updated"
else
  echo "skipping UID configuration"
fi

if [ -n "${USER_GID}" ] && [ "${USER_GID}" != "`id -g ${USER}`" ] ; then
  echo -n "Update gid for group ${USER} with ${USER_GID}"
  usermod -u ${USER_UID} ${USER}
  echo "... updated"
else
  echo "skipping GID configuration"
fi

# Ensure PATH includes ~/.local/bin and ~/.npm/bin in fish config
FISH_CONFIG="/home/${USER}/.config/fish/config.fish"
mkdir -p "$(dirname "$FISH_CONFIG")"
grep -q 'fish_add_path -g ~/.local/bin' "$FISH_CONFIG" 2>/dev/null || echo 'fish_add_path -g ~/.local/bin' >> "$FISH_CONFIG"
grep -q 'fish_add_path -g ~/.npm/bin' "$FISH_CONFIG" 2>/dev/null || echo 'fish_add_path -g ~/.npm/bin' >> "$FISH_CONFIG"

# Install Oh My Fish + bobthefish if not already present
if [ ! -d "/home/${USER}/.local/share/omf" ]; then
  curl -sS "https://raw.githubusercontent.com/oh-my-fish/oh-my-fish/master/bin/install" > /tmp/install_omf \
    && fish /tmp/install_omf --noninteractive \
    && rm /tmp/install_omf \
    && fish -c "omf install bobthefish"
fi

# Install Claude Code if not already present
if ! command -v claude &>/dev/null && [ ! -f "/home/${USER}/.npm/bin/claude" ]; then
  mkdir -p "/home/${USER}/.npm"
  npm config set prefix "/home/${USER}/.npm"
  npm install -g @anthropic-ai/claude-code
fi

# Re-install netbox-wdm in case source changed
uv pip install --no-cache-dir -e /opt/netbox-wdm

exec "$@"
