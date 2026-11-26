#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
version=$(sed -n 's/^VERSION = "\(.*\)"$/\1/p' etherdeck/__init__.py)
test -n "$version"
test -s bridge-firmware/manifest.json
test -s bridge-firmware/firmware.bin
test -s bridge-firmware/bootstrap.bin
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
app="$stage/usr/share/APPLaunch"
payload="$app/apps/etherdeck"
install -d -m 0755 "$stage/DEBIAN" "$app/bin" "$app/applications" "$app/share/images" \
    "$payload/etherdeck" "$payload/bridge-firmware" "$stage/usr/share/doc/etherdeck"
chmod 0755 "$stage"
install -m 0755 packaging/etherdeck.sh "$app/bin/etherdeck"
install -m 0644 packaging/etherdeck.desktop "$app/applications/etherdeck.desktop"
install -m 0644 packaging/etherdeck_100.png "$app/share/images/etherdeck_100.png"
install -m 0644 etherdeck/*.py "$payload/etherdeck/"
install -m 0644 bridge-firmware/manifest.json bridge-firmware/*.bin "$payload/bridge-firmware/"
install -m 0644 LICENSE "$stage/usr/share/doc/etherdeck/copyright"
install -m 0644 THIRD_PARTY.md "$stage/usr/share/doc/etherdeck/"
cat > "$stage/DEBIAN/control" <<CTL
Package: etherdeck
Version: $version
Architecture: all
Maintainer: Pocket RF OS local build <etherdeck@localhost>
Depends: python3 (>= 3.11), python3-pil, python3-numpy, python3-serial, fonts-noto-cjk, ca-certificates
Suggests: esptool
Section: electronics
Priority: optional
Description: Pocket RF OS RF module bench for CardputerZero
 Native APPLaunch interface for CC1101, nRF24L01+ and SX127x LoRa
 using the EtherDeck firmware on a USB-connected Cardputer ADV.
CTL
chmod 0644 "$stage/DEBIAN/control"
mkdir -p dist
dpkg-deb --root-owner-group --build "$stage" "dist/etherdeck_${version}_all.deb"
