#!/bin/sh
set -eu
cd /usr/share/APPLaunch/apps/etherdeck
exec /usr/bin/python3 -m etherdeck "$@"
