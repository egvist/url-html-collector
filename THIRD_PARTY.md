# Third-party dependencies

This repository contains the collector's source code and dependency declarations. It does not bundle CloakBrowser's wrapper source or compiled browser binary.

## CloakBrowser

- Project: https://github.com/CloakHQ/CloakBrowser
- Wrapper license: [MIT](https://github.com/CloakHQ/CloakBrowser/blob/main/LICENSE), copyright CloakHQ.
- Compiled browser: governed separately by the [CloakBrowser Binary License](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md).

Users install the Python dependency and obtain browser downloads through CloakBrowser's official distribution channels. Dependency listing is addressed in the binary license's integration-use section. This project's MIT license does not grant rights to third-party binaries or override their terms. Browser binaries and license keys must not be committed to this repository.

## Playwright

The collector also uses the Playwright API, installed through CloakBrowser's dependencies. Playwright is [Apache-2.0 licensed](https://github.com/microsoft/playwright-python/blob/main/LICENSE).
