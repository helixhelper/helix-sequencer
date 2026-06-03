# Support Matrix

This document outlines the officially supported platforms, versions, and dependencies for the Helix Sequencer.

## Operating Systems

| OS | Status | Notes |
|---|---|---|
| **Windows 10/11** | ✅ Supported | Primary development and test platform |
| **Windows Server 2019+** | ✅ Supported | Suitable for automated/headless rendering |
| **macOS 12+** (Intel) | ⚠️ Limited | Community support; not regularly tested |
| **macOS 13+** (Apple Silicon) | ⚠️ Limited | Community support; not regularly tested |
| **Linux (Ubuntu 20.04+)** | ⚠️ Limited | Community support; WSL on Windows also supported |

## Python Versions

| Version | Status | Notes |
|---|---|---|
| **3.11** | ✅ Supported | Stable, well-tested |
| **3.12** | ✅ Supported | Latest stable, full compatibility |
| **3.10** | ⚠️ Limited | Community support; no active testing |
| **3.9 and earlier** | ❌ Unsupported | End of life or lacking required features |

## xLights Versions

| Version | Status | Notes |
|---|---|---|
| **2023.x** | ✅ Supported | Primary target version |
| **2024.x** | ✅ Supported | Tested and compatible |
| **2022.x** | ⚠️ Limited | May work; no active support |
| **2021.x and earlier** | ❌ Unsupported | Incompatible with current sequencer output |

## Dependency Versions

Core dependencies with tested version ranges:

| Package | Min Version | Tested | Notes |
|---|---|---|---|
| `numpy` | 1.20.0 | 1.24+ | Array processing |
| `pyyaml` | 5.4 | 6.0+ | Configuration parsing |
| `pytest` | 6.0 | 7.4+ | Testing framework (dev only) |

## Graphics and Rendering

| Component | Requirement | Notes |
|---|---|---|
| **GPU Support** | Optional | CPU-only rendering fully supported; GPU acceleration not required |
| **Display** | Not required | Headless operation fully supported for server environments |

## Known Limitations

- **Unicode paths:** Some xLights asset paths with non-ASCII characters may require manual intervention
- **Network shares:** SMB paths generally work; NFS support is limited
- **Large sequences:** Sequences exceeding 60 minutes may require increased memory allocation
- **Concurrent runs:** Multiple simultaneous sequencer instances on the same system require separate output directories

## Getting Help

- Check the [README](../README.md) for quick start instructions
- See [BETA_POLICY.md](./BETA_POLICY.md) for data and privacy information
- Review existing [GitHub Issues](https://github.com/ryankorkowski-boop/helix-sequencer/issues) for known problems
- For bugs or feature requests, open a new issue with platform details and reproduction steps
