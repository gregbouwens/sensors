# Ensure architecture is correct:
uname -m
## Should return: aarch64


# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
node --version
npm --version

# Install Claude
## Remove old versions if present
npm uninstall -g @anthropic-ai/claude-code

## Install older working version
npm install -g @anthropic-ai/claude-code@0.2.114


mkdir -p ~/.npm-global

npm config set prefix '~/.npm-global'

echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

npm install -g @anthropic-ai/claude-code@0.2.114
