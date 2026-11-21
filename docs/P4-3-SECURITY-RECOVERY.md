# R1 P4-3 — security, private backup and recovery software gate

This is a **draft** software-only PR dependent on P4-2 PR #15. Do not merge, flash, release or touch eFuse based on a green GitHub CI.

## Official NVS encryption decision

Espressif ESP-IDF v6.1 NVS native encryption has two supported protection schemes:

1. Flash-encryption-backed NVS needs Flash Encryption and a separate encrypted **data/nvs_keys** partition. Original 4B 16MiB partition layout has no such partition.
2. HMAC-backed NVS can avoid a separate key partition, but the standard **nvs_flash_init** path may generate an HMAC key and irreversibly write eFuse on its first invocation when encryption is configured.

Therefore this branch **does not enable CONFIG_NVS_ENCRYPTION** and does not re-partition, automatically migrate existing plain NVS, burn eFuse, enable Secure Boot, overwrite otadata, or alter the original Xiaozhi 16MiB flash layout. All current P4-2 SS2022/VLESS/AP credential storage remains **unencrypted development-only NVS**. This is a release-blocking security gap, not a claim of production encryption. Do not invent an app cryptosystem as a substitute for the official Espressif implementation.

Official sources:
- https://docs.espressif.com/projects/esp-idf/en/v6.1/esp32s3/api-reference/storage/nvs_encryption.html
- https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/system/ota.html
- https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/security/flash-encryption.html

## Read-only full-Flash backup and verification

Original partition invariants: nvs: 0x9000 / 0x4000; otadata: 0xd000 / 0x2000; phy_init: 0xf000 / 0x1000; ota_0: 0x20000 / 0x3f0000; ota_1: 0x410000 / 0x3f0000; assets: 0x800000 / 0x800000.

1. After checking the exact S3 model and physical port, install official esptool on your own computer.
2. For a first backup, run **only locally**:
   python tools/p4_flash_backup.py capture --port /dev/cu.usbmodemXXXX --out ./s3-r1-private-backup
3. To verify previously captured bytes without touching the device:
   python tools/p4_flash_backup.py verify --dir ./s3-r1-private-backup
4. This creates a private 16MiB **fullflash-private.bin** and private **manifest.json**, verifies per-partition SHA256, original layout, OTA image header and exact full length. Host tests inject synthetic Flash bytes and fake esptool. **Real restore and flash operations are not implemented.**
5. **Do not upload the full Flash backup, NVS dump, logs containing credentials or manifest to GitHub or this chat.** Keep a protected offline copy.
6. Hardware recovery must still verify actual bootloader, OTA slot, security/eFuse status and test a reversible restoration process before any flash write is authorized.

## Production release

The tool **tools/p4_release_gate.py** deliberately blocks release unless the physical 4B hardware acceptance evidence covers actual backup hash, practical restore, Xiaozhi voice/LCD, both VPS encrypted paths, leak tests, operator authorization and **native NVS encryption on the real device**. A CI pass only demonstrates that an unsafe release is refused. Reviewer must validate any manually submitted evidence; it is not cryptographic attestation.

Next real-world acceptance: combine P4-2 + P4-3 in ONE S3 hardware session after verified backup; no automatic eFuse burning or destructive OTA/Flash actions. P4-3 software recovery tools may pass host/IDF CI while production release stays blocked by design.

## Stage accounting

P0, P1, P2, P3 finished; P4-1 35% of P4 complete. P4-2 and P4-3 remain pending real device acceptance. P4-3 is one PR weighted 25% of P4 and must not be marked 100% by software CI alone. Noncritical speculative robustness (<20% estimated probability) is deferred.