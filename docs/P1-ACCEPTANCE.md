# P1-4 集中回归与验收记录

状态：**P1 源码及自动化验收已通过，PR #7 已合并。P4 真机未验收。**
上游源版本固定：yanxke/ESP32-VPN-Transparent-Proxy-Router@dfb04b03154cfaee1d8615e4b8942dfe737abc5d，MIT。未修改上游仓库；CI 顺序应用 patches/0001～0004。

## 需求与检查矩阵

| 场景 | 预期 | 证据类型 |
|---|---|---|
| 28/39 字节短 UDP，UDP/443 QUIC，外部 DNS/53，广播非 DHCP | AP 入站截获后丢弃，不新建 XUDP 流 | 实际 C IPv4 hook 的宿主机合成数据包 |
| UDP/68→67 DHCP 与 AP 本地 UDP/53 DNS、AP 管理 TCP | 保留原有本地协议处理 | 实际 C hook 的入口放行；**不是完整 DHCP/DNS 服务成功** |
| IPv4 头 IHL=60，TCP/UDP | 读取传输头时不使用固定 header[60] 越界 | GCC ASan/UBSan 编译与实际 C hook 测试 |
| IPv4 初片/非首片及不支持的外部协议 | fail closed，无普通上游转发 | 实际 C hook 的宿主机合成数据包 |
| 无状态 TCP ACK、100 条流表耗尽、内存分配/报文复制/重写失败 | 丢弃而非 return 0 允许普通 IP 路径处理 | 实际 C hook 的宿主机故障注入 |
| TCP SYN 正常 | 原 lwIP 流表恢复、重写至 AP:15001、调用原 ip4_input 重入 | 实际 C hook 测试 |
| AP 以外接口输入 | 保持原逻辑，不错误接管 STA 流量 | 实际 C hook 测试 |
| DNS A 记录缓存 | 原缓存记录与按 IP 查询可正常工作 | 宿主机执行原 C 缓存函数 |
| BOOT/网页/串口 direct 路由切换 | TCP-only 固件拒绝切换为上游直连 | 源码控制流检查；实机需 P4 |
| STA 断开、透明截获状态 | 保持 AP 入口拦截启用 | 源码检查；实际断网留 P4 |
| 代理 DNS 隧道失败 | 不将远端域名映射到 AP 地址；返回 DNS SERVFAIL | 源码检查；真实 DNS 交互留 P4 |
| 4B AP+STA、手机透明访问、实际 DNS/断线/IPv6 | 完整系统联调 | **P4 专属实机验收，P1 不计入** |

## 修复说明

- 0001：TCP-only UDP 基础拦截和短包入口，初版已在 PR #5 验证。
- 0002：去除直连旁路与断线上游时截获关闭，已在 PR #6 验证。
- 0003：校验 IP 总长和分片，正确读取可变 IHL 后的 TCP/UDP 头，所有异常 TCP 入站失败路径消耗并释放 pbuf（按 lwIP Hook 的所有权语义）。
- 0004：原 captive_dns_task 在代理 DNS 失败时会回答本地网关地址；TCP-only 正常代理模式下改返回 DNS SERVFAIL，**明确进入配网模式时保留原 Captive Portal DNS**。

## 源码与官方依据

- lwIP Hook：返回 0 = 没消费，继续普通处理；非 0 = 自己负责释放。https://www.nongnu.org/lwip/2_1_x/group__lwip__opts__hooks.html
- ESP-IDF ESP32-S3 lwIP 官方 IPv4 hook 指导：https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/lwip.html
- 固定源文件：https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router/blob/dfb04b03154cfaee1d8615e4b8942dfe737abc5d/src/transparent_tcp.c
- DNS 与路由入口：https://github.com/yanxke/ESP32-VPN-Transparent-Proxy-Router/blob/dfb04b03154cfaee1d8615e4b8942dfe737abc5d/src/main.c

## 已知剩余风险与 P4 交接

- Host shims 没有硬件 Wi-Fi 任务、lwIP netif 竞态和真实分片队列；只说明已执行的 C 入站函数测试通过，不声称实际 Wi-Fi 不泄漏。
- DNS SERVFAIL 的 wire-format 需用真实 DNS 客户端确认。DNS-over-VLESS 初期仍是原版纯 TCP；P3 才引入标准验证的 TLS。
- 在 P4 之前，不允许向真实 4B 覆盖既有小智固件。NVS/默认密码/网络页面和 LCD、音频资源需要独立验收。
- P2/P3 的 SS2022/TLS/IPv6 编译、协议互通与 VPS 必须分别通过，不可用 P1 原 VLESS 原版编译代替。

## CI 验收结果

- [PR #7](https://github.com/Jackyhuang83/s3-voice-4b-proxy/pull/7) 已经合并到 main，merge SHA = a7692a898c08c5ec00bb2bd78104225ab21f6f0d。
- [实际 CI Run](https://github.com/Jackyhuang83/s3-voice-4b-proxy/actions/runs/44875289360)：四份补丁应用、静态策略顺序与 clang-format 均 PASS。
- Host 测试：针对原版 transparent_tcp.c 执行 **23 个**合成报文、故障注入、资源耗尽场景；ASan 与 UBSan PASS。
- 修改后 PlatformIO `esp32s3_r8n16` 编译 PASS（S3_PROXY_TCP_ONLY=1）。
- P0 文档检查、原版编译及上游质量检查在该 PR Head SHA 上均 PASS。
- **NOT RUN / P4 待验收**：4B 实机 AP+STA、真实客户端 DNS/DHCP、断线防泄漏、LCD/语音兼容性。

## 回退

所有补丁只在项目 CI 检出的临时上游副本上应用；移除相应 patches/0003、0004 引用可恢复旧版 0001/0002 编译。旧版并非安全可发布固件，不构成安全回退基线。
