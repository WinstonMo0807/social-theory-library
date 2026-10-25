#!/bin/sh
# Mounted only by compose.stl4-preview.yaml, after nginx's template expansion.
set -eu
sed -i 's/add_header X-Frame-Options DENY always;/add_header X-Frame-Options SAMEORIGIN always;/' /etc/nginx/conf.d/default.conf
